package requester

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/felipemarinho97/torrent-indexer/logging"
	"github.com/felipemarinho97/torrent-indexer/utils"
)

type FlareSolverr struct {
	url         string
	maxTimeout  int
	httpClient  *http.Client
	sessionPool chan string
	mu          sync.Mutex
	initiated   atomic.Bool
	useSessions bool
}

var (
	ErrListSessions = fmt.Errorf("failed to list sessions")
)

func NewFlareSolverr(url string, timeoutMilli int, poolSize int) *FlareSolverr {
	if poolSize <= 0 {
		poolSize = 5
	}
	httpClient := &http.Client{
		Timeout: time.Duration(timeoutMilli) * time.Millisecond,
	}
	sessionPool := make(chan string, poolSize)
	useSessions := false
	if value := strings.TrimSpace(os.Getenv("FLARESOLVERR_USE_SESSIONS")); value != "" {
		if parsed, err := strconv.ParseBool(value); err == nil {
			useSessions = parsed
		}
	}

	f := &FlareSolverr{
		url:         url,
		maxTimeout:  timeoutMilli,
		httpClient:  httpClient,
		sessionPool: sessionPool,
		useSessions: useSessions,
	}

	if url == "" {
		logging.Info().Msg("FlareSolverr is not configured (FLARESOLVERR_ADDRESS empty); Cloudflare-protected indexers will be unavailable")
		return f
	}

	if !useSessions {
		f.initiated.Store(true)
		logging.Info().Msg("FlareSolverr session reuse disabled; using sessionless requests")
		return f
	}

	// Do not block the HTTP server startup on FlareSolverr. The pool is
	// initialized in the background and requests to protected sites simply
	// fail fast until it is ready.
	logging.Info().Str("address", url).Msg("Initializing FlareSolverr session pool in background")
	go f.initialize()

	return f
}

func (f *FlareSolverr) initialize() {
	const maxAttempts = 6
	const retryDelay = 5 * time.Second

	initClient := &http.Client{Timeout: 10 * time.Second}

	for attempt := 1; attempt <= maxAttempts; attempt++ {
		err := f.fillSessionPool(initClient)
		if err == nil && len(f.sessionPool) > 0 {
			f.initiated.Store(true)
			logging.Info().Int("sessions", len(f.sessionPool)).Msg("FlareSolverr session pool ready")
			return
		}

		if err != nil {
			logging.Warn().Err(err).Int("attempt", attempt).Int("max_attempts", maxAttempts).Msg("FlareSolverr not ready yet; retrying")
		} else {
			logging.Warn().Int("attempt", attempt).Int("max_attempts", maxAttempts).Msg("FlareSolverr session pool is empty; retrying")
		}

		if attempt < maxAttempts {
			time.Sleep(retryDelay)
		}
	}

	logging.Error().Msg("Failed to initialize FlareSolverr session pool; protected indexers will be unavailable")
}

func (f *FlareSolverr) FillSessionPool() error {
	return f.fillSessionPool(f.httpClient)
}

func (f *FlareSolverr) fillSessionPool(client *http.Client) error {
	// Check if the pool is already filled
	if len(f.sessionPool) == cap(f.sessionPool) {
		return nil
	}

	// Pre-initialize the pool with existing sessions
	sessions, err := f.listSessions(client)
	if err != nil {
		// if fail to list sessions, it may not support the sessions.list command
		// create new dumb sessions to fill the pool
		if err == ErrListSessions {
			for len(f.sessionPool) < cap(f.sessionPool) {
				f.sessionPool <- "dumb-session"
			}
			return nil
		}
		logging.Error().Err(err).Msg("Failed to list existing FlareSolverr sessions")
		return err
	}

	for _, session := range sessions {
		// Add available sessions to the pool
		if len(f.sessionPool) < cap(f.sessionPool) {
			f.sessionPool <- session
		}
	}
	if len(f.sessionPool) > 0 {
		logging.Info().Int("sessions", len(f.sessionPool)).Msg("Added FlareSolverr sessions to the pool")
	}

	// If fewer than poolSize sessions were found, create new ones to fill the
	// pool. Bound the attempts to avoid an infinite loop when the FlareSolverr
	// instance keeps rejecting session creation.
	for attempts := 0; attempts < cap(f.sessionPool) && len(f.sessionPool) < cap(f.sessionPool); attempts++ {
		if f.createSession(client) == "" {
			break
		}
	}

	if len(f.sessionPool) == 0 {
		return fmt.Errorf("no FlareSolverr sessions available")
	}

	return nil
}

func (f *FlareSolverr) CreateSession() string {
	return f.createSession(f.httpClient)
}

func (f *FlareSolverr) createSession(client *http.Client) string {
	f.mu.Lock()
	defer f.mu.Unlock()

	body := map[string]string{"cmd": "sessions.create"}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return ""
	}

	req, err := http.NewRequest("POST", fmt.Sprintf("%s/v1", f.url), bytes.NewBuffer(jsonBody))
	if err != nil {
		return ""
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return ""
	}

	defer resp.Body.Close()

	var sessionResponse map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&sessionResponse)
	if err != nil {
		return ""
	}

	session, ok := sessionResponse["session"].(string)
	if !ok {
		logging.Error().Msg("Failed to create FlareSolverr session")
		return ""
	}
	// Add session to the pool
	f.sessionPool <- session

	logging.Info().Str("session", session).Msg("Created new FlareSolverr session")
	return session
}

func (f *FlareSolverr) ListSessions() ([]string, error) {
	return f.listSessions(f.httpClient)
}

func (f *FlareSolverr) listSessions(client *http.Client) ([]string, error) {
	body := map[string]string{"cmd": "sessions.list"}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequest("POST", fmt.Sprintf("%s/v1", f.url), bytes.NewBuffer(jsonBody))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}

	defer resp.Body.Close()

	var sessionsResponse map[string]interface{}
	err = json.NewDecoder(resp.Body).Decode(&sessionsResponse)
	if err != nil {
		return nil, err
	}
	if sessionsResponse["sessions"] == nil {
		return nil, ErrListSessions
	}

	sessions := sessionsResponse["sessions"].([]interface{})
	var sessionIDs []string
	for _, session := range sessions {
		sessionIDs = append(sessionIDs, session.(string))
	}

	return sessionIDs, nil
}

func (f *FlareSolverr) RetrieveSession(ctx context.Context) (string, error) {
	// Blocking receive from the session pool.
	select {
	case session := <-f.sessionPool:
		return session, nil
	case <-ctx.Done():
		return "", ctx.Err()
	}
}

type Response struct {
	Status   string `json:"status"`
	Message  string `json:"message"`
	Solution struct {
		Url     string `json:"url"`
		Status  int    `json:"status"`
		Cookies []struct {
			Domain   string `json:"domain"`
			Expiry   int    `json:"expiry"`
			HttpOnly bool   `json:"httpOnly"`
			Name     string `json:"name"`
			Path     string `json:"path"`
			SameSite string `json:"sameSite"`
			Secure   bool   `json:"secure"`
			Value    string `json:"value"`
		} `json:"cookies"`
		UserAgent string          `json:"userAgent"`
		Headers   json.RawMessage `json:"headers"`
		Response  string          `json:"response"`
	} `json:"solution"`
}

func (f *FlareSolverr) Get(ctx context.Context, _url string, attempts int) (io.ReadCloser, error) {
	// Check if the FlareSolverr instance was initiated
	if !f.initiated.Load() {
		logging.Debug().Str("url", _url).Msg("FlareSolverr is not ready yet; returning empty response")
		return io.NopCloser(bytes.NewReader([]byte(""))), nil
	}

	session := ""
	if f.useSessions {
		var err error
		session, err = f.RetrieveSession(ctx)
		if err != nil {
			return nil, err
		}

		// Ensure the session is returned to the pool after the request is done
		defer func() {
			f.sessionPool <- session
		}()
	}

	body := map[string]interface{}{
		"cmd":        "request.get",
		"url":        _url,
		"maxTimeout": f.maxTimeout,
	}
	if f.useSessions {
		body["session"] = session
	}
	jsonBody, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}

	req, err := http.NewRequestWithContext(ctx, "POST", fmt.Sprintf("%s/v1", f.url), bytes.NewBuffer(jsonBody))
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := f.httpClient.Do(req)
	if err != nil {
		return nil, err
	}

	// Parse the response
	var response Response
	err = json.NewDecoder(resp.Body).Decode(&response)
	if err != nil {
		return nil, err
	}

	// Check if the response was successful
	if response.Status != "ok" {
		// if is 500 Internal Server Error, recursively call the Get method
		if resp.StatusCode == http.StatusInternalServerError && attempts != 0 {
			attempts--
			logging.Warn().Str("url", _url).Int("attempts_left", attempts).Msg("FlareSolverr Internal Server Error, retrying")
			return f.Get(ctx, _url, attempts) // Retry the request
		}

		// log the http status code
		return nil, fmt.Errorf("failed to get response: %s, statusCode: %s", response.Message, resp.Status)
	}

	// Check if "Under attack" is in the response
	if strings.Contains(response.Solution.Response, "Under attack") {
		return nil, fmt.Errorf("under attack")
	}

	// check if the response is valid HTML
	if !utils.IsValidHTML(response.Solution.Response) {
		logging.Warn().Str("url", _url).Msg("FlareSolverr returned invalid HTML response")
		logging.Debug().Str("url", _url).Str("response", response.Solution.Response).Msg("FlareSolverr response content")
		response.Solution.Response = ""
	}

	// If the response body is empty but cookies are present, make a new request
	if response.Solution.Response == "" && len(response.Solution.Cookies) > 0 {
		logging.Debug().Str("url", _url).Msg("FlareSolverr making new request with cookies")
		// Create a new request with cookies
		client := &http.Client{
			Timeout: time.Duration(f.maxTimeout) * time.Millisecond,
		}
		cookieJar, err := cookiejar.New(&cookiejar.Options{})
		if err != nil {
			return nil, err
		}
		for _, cookie := range response.Solution.Cookies {
			cookieJar.SetCookies(&url.URL{Host: cookie.Domain}, []*http.Cookie{
				{
					Name:   cookie.Name,
					Value:  cookie.Value,
					Domain: cookie.Domain,
					Path:   cookie.Path,
				},
			})
		}
		client.Jar = cookieJar

		secondReq, err := http.NewRequestWithContext(ctx, "GET", _url, nil)
		if err != nil {
			return nil, err
		}

		// use the same user returned by the FlareSolverr
		secondReq.Header.Set("User-Agent", response.Solution.UserAgent)

		secondResp, err := client.Do(secondReq)
		if err != nil {
			return nil, err
		}

		respByte := new(bytes.Buffer)
		_, err = respByte.ReadFrom(secondResp.Body)
		if err != nil {
			return nil, err
		}

		// Return the body of the second request
		return io.NopCloser(bytes.NewReader(respByte.Bytes())), nil
	}

	// Return the original response body
	return io.NopCloser(bytes.NewReader([]byte(response.Solution.Response))), nil
}
