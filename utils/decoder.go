package utils

import (
	"encoding/base64"
	"fmt"
	"html"
	"net/url"
	"strings"
)

func DecodeAdLink(encodedStr string) (string, error) {
	if encodedStr == "" {
		return "", fmt.Errorf("empty string")
	}
	reversed := reverseString(encodedStr)

	decodedBytes, err := base64.StdEncoding.DecodeString(reversed)
	if err != nil {
		return "", err
	}

	htmlUnescaped := html.UnescapeString(string(decodedBytes))

	return htmlUnescaped, nil
}

func Base64Decode(input string) (string, error) {
	if input == "" {
		return "", fmt.Errorf("empty string")
	}
	decodedBytes, err := base64.StdEncoding.DecodeString(input)
	if err != nil {
		return "", err
	}
	return string(decodedBytes), nil
}

// Helper function to reverse a string
func reverseString(s string) string {
	runes := []rune(s)
	for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
		runes[i], runes[j] = runes[j], runes[i]
	}
	return string(runes)
}

// unshuffleStringByStep reconstructs an original string from a shuffled version.
// The input was created by picking characters using a stepping cursor (advancing
// by step positions through the original, skipping already-used positions).
// This function inverts the process: it walks the same cursor sequence and places
// each shuffled[i] back into original[index].
func unshuffleStringByStep(shuffled string, step int) (string, error) {
	runes := []rune(shuffled)
	length := len(runes)
	if length == 0 {
		return "", fmt.Errorf("empty string")
	}
	if step <= 0 {
		return "", fmt.Errorf("step must be greater than 0")
	}

	original := make([]rune, length)
	used := make([]bool, length)
	index := 0

	for i := 0; i < length; i++ {
		for used[index] {
			index = (index + 1) % length
		}
		used[index] = true
		original[i] = runes[index]
		index = (index + step) % length
	}

	return string(original), nil
}

// UnshuffleStringByStep reconstructs a string that was shuffled with the same
// stepping cursor algorithm. It is used by the Starck Filmes download resolver.
func UnshuffleStringByStep(shuffled string, step int) (string, error) {
	return unshuffleStringByStep(shuffled, step)
}

// DecodeStarckDataU decodes the obfuscated magnet link from the data-u attribute. This is indexer-specific.
func DecodeStarckDataU(dataU string) (string, error) {
	if dataU == "" {
		return "", fmt.Errorf("empty data-u value")
	}

	unshuffled, err := unshuffleStringByStep(dataU, 3)
	if err != nil {
		return "", fmt.Errorf("unshuffle failed: %w", err)
	}

	if !IsMagnetLink(unshuffled) {
		return "", fmt.Errorf("decoded string is not a valid magnet link: %s", unshuffled)
	}

	return unshuffled, nil
}

func IsMagnetLink(link string) bool {
	return len(link) > 8 && link[:8] == "magnet:?"
}

func DecodeSystemAdsLink(encodedURL string) (string, error) {
	u, err := url.Parse(encodedURL)
	if err != nil {
		return "", fmt.Errorf("invalid systemads URL: %w", err)
	}
	idParam := u.Query().Get("id")
	if idParam == "" {
		return "", fmt.Errorf("no 'id' parameter in systemads URL")
	}

	idParam, err = url.PathUnescape(idParam)
	if err != nil {
		return "", fmt.Errorf("failed to URL-decode id: %w", err)
	}
	idParam = strings.ReplaceAll(idParam, " ", "+")

	link, err := decodeSystemAdsID(idParam)
	if err == nil && IsMagnetLink(link) {
		return link, nil
	}
	if err == nil && len(link) > 7 && (link[:7] == "http://" || link[:8] == "https://") {
		return link, nil
	}

	if err != nil {
		return "", fmt.Errorf("failed to decode systemads id: %w", err)
	}
	return "", fmt.Errorf("decoded systemads id is not a magnet or HTTP link: %s", link)
}

func decodeSystemAdsID(id string) (string, error) {
	decodedBytes, err := base64.StdEncoding.DecodeString(id)
	if err == nil {
		decoded := string(decodedBytes)
		if len(decoded) > 0 {
			return decoded, nil
		}
	}

	decodedBytes, err = base64.RawStdEncoding.DecodeString(id)
	if err == nil {
		decoded := string(decodedBytes)
		if len(decoded) > 0 {
			return decoded, nil
		}
	}

	decodedBytes, err = base64.URLEncoding.DecodeString(id)
	if err == nil {
		decoded := string(decodedBytes)
		if len(decoded) > 0 {
			return decoded, nil
		}
	}

	if len(id) > 0 {
		reversed := reverseString(id)
		decodedBytes, err = base64.StdEncoding.DecodeString(reversed)
		if err == nil {
			decoded := html.UnescapeString(string(decodedBytes))
			if len(decoded) > 0 {
				return decoded, nil
			}
		}
	}

	return "", fmt.Errorf("all decoding strategies failed for: %s", id)
}
