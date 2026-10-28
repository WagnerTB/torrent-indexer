package handler

import (
	"context"
	"encoding/base64"
	"fmt"
	"html"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/felipemarinho97/torrent-indexer/utils"
)

var starckMagnetRE = regexp.MustCompile(`magnet:\?[^"'\s<>]+`)

func newStarckHTTPClient() *http.Client {
	jar, _ := cookiejar.New(nil)
	return &http.Client{
		Timeout: 30 * time.Second,
		Jar:     jar,
	}
}

// resolveFilmedlMagnet follows the filmedl.com redirect chain until it finds
// the magnet link encoded in the final page (body data-id attribute).
func resolveFilmedlMagnet(ctx context.Context, rawURL, referer string) (string, error) {
	client := newStarckHTTPClient()

	body, finalURL, err := starckGet(ctx, client, rawURL, referer)
	if err != nil {
		return "", err
	}

	for step := 0; step < 14; step++ {
		if magnetLink := findMagnetInText(body); magnetLink != "" {
			return magnetLink, nil
		}

		doc, err := goquery.NewDocumentFromReader(strings.NewReader(body))
		if err != nil {
			return "", fmt.Errorf("failed to parse filmedl response: %w", err)
		}

		if dataID, ok := doc.Find("body").Attr("data-id"); ok {
			dataID = strings.TrimSpace(html.UnescapeString(dataID))
			if dataID != "" {
				// Some chains expose another filmedl URL in data-id before the
				// final page that contains the encoded magnet.
				if parsed, err := url.Parse(dataID); err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") {
					if strings.HasSuffix(strings.ToLower(parsed.Hostname()), "filmedl.com") {
						body, finalURL, err = starckGet(ctx, client, dataID, finalURL)
						if err != nil {
							return "", err
						}
						continue
					}
				}

				if magnetLink, err := decodeFilmedlDataID(dataID); err == nil {
					return magnetLink, nil
				}
			}
		}

		action, method, values, ok := extractStarckForm(doc)
		if !ok {
			break
		}

		base, err := url.Parse(finalURL)
		if err != nil {
			return "", fmt.Errorf("failed to parse current URL: %w", err)
		}
		actionURL, err := base.Parse(action)
		if err != nil {
			return "", fmt.Errorf("failed to parse form action: %w", err)
		}

		if strings.EqualFold(method, http.MethodGet) {
			query := actionURL.Query()
			for key, vals := range values {
				for _, val := range vals {
					query.Set(key, val)
				}
			}
			actionURL.RawQuery = query.Encode()
			body, finalURL, err = starckGet(ctx, client, actionURL.String(), finalURL)
		} else {
			body, finalURL, err = starckPostForm(ctx, client, actionURL.String(), finalURL, values)
		}
		if err != nil {
			return "", err
		}
	}

	return "", fmt.Errorf("no magnet found in filmedl redirect chain")
}

func starckGet(ctx context.Context, client *http.Client, rawURL, referer string) (string, string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return "", "", err
	}
	starckSetHeaders(req, referer)

	resp, err := client.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", "", err
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return "", "", fmt.Errorf("unexpected status %s for %s", resp.Status, rawURL)
	}

	return string(body), resp.Request.URL.String(), nil
}

func starckPostForm(ctx context.Context, client *http.Client, action, referer string, values url.Values) (string, string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, action, strings.NewReader(values.Encode()))
	if err != nil {
		return "", "", err
	}
	starckSetHeaders(req, referer)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := client.Do(req)
	if err != nil {
		return "", "", err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", "", err
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return "", "", fmt.Errorf("unexpected status %s for %s", resp.Status, action)
	}

	return string(body), resp.Request.URL.String(), nil
}

func starckSetHeaders(req *http.Request, referer string) {
	req.Header.Set("User-Agent", utils.SpoofedUserAgent)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "pt-BR,pt;q=0.9,en;q=0.8")
	if referer != "" {
		req.Header.Set("Referer", referer)
	}
}

func extractStarckForm(doc *goquery.Document) (string, string, url.Values, bool) {
	form := doc.Find("form").First()
	if form.Length() == 0 {
		return "", "", nil, false
	}

	action, _ := form.Attr("action")
	if strings.TrimSpace(action) == "" {
		return "", "", nil, false
	}

	method, _ := form.Attr("method")
	if method == "" {
		method = http.MethodGet
	}

	values := url.Values{}
	form.Find("input").Each(func(_ int, s *goquery.Selection) {
		name, ok := s.Attr("name")
		if !ok || name == "" {
			return
		}
		value, _ := s.Attr("value")
		values.Set(name, value)
	})

	return action, method, values, true
}

func findMagnetInText(body string) string {
	match := starckMagnetRE.FindString(body)
	if match == "" {
		return ""
	}
	return html.UnescapeString(match)
}

func decodeFilmedlDataID(dataID string) (string, error) {
	if dataID == "" {
		return "", fmt.Errorf("empty data-id")
	}

	unshuffled, err := utils.UnshuffleStringByStep(dataID, 3)
	if err == nil {
		if magnetLink := decodeMagnetFromBase64(unshuffled); magnetLink != "" {
			return magnetLink, nil
		}
	}

	if magnetLink := decodeMagnetFromBase64(dataID); magnetLink != "" {
		return magnetLink, nil
	}

	return "", fmt.Errorf("could not decode data-id")
}

func decodeMagnetFromBase64(value string) string {
	encodings := []*base64.Encoding{
		base64.RawURLEncoding,
		base64.RawStdEncoding,
	}

	padded := value
	for len(padded)%4 != 0 {
		padded += "="
	}
	encodings = append(encodings, base64.URLEncoding, base64.StdEncoding)

	for _, encoding := range encodings {
		decodedBytes, err := encoding.DecodeString(padded)
		if err != nil {
			decodedBytes, err = encoding.DecodeString(value)
		}
		if err != nil {
			continue
		}

		decoded := string(decodedBytes)
		if idx := strings.Index(decoded, "magnet:"); idx >= 0 {
			return html.UnescapeString(decoded[idx:])
		}
	}

	return ""
}
