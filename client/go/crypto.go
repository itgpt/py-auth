package authclient

import (
	"crypto/sha256"
	"encoding/base64"
	"errors"

	"github.com/fernet/fernet-go"
)

func EncryptData(data []byte, clientSecret string) (string, error) {
	if clientSecret == "" {
		return "", errors.New("client_secret不能为空")
	}

	hash := sha256.Sum256([]byte(clientSecret))
	keyBytes := base64.URLEncoding.EncodeToString(hash[:32])

	key, err := fernet.DecodeKey(keyBytes)
	if err != nil {
		return "", err
	}

	token, err := fernet.EncryptAndSign(data, key)
	if err != nil {
		return "", err
	}
	return string(token), nil
}

func DecryptData(encryptedData string, clientSecret string) ([]byte, error) {
	if clientSecret == "" {
		return nil, errors.New("client_secret不能为空")
	}

	hash := sha256.Sum256([]byte(clientSecret))
	keyBytes := base64.URLEncoding.EncodeToString(hash[:32])

	key, err := fernet.DecodeKey(keyBytes)
	if err != nil {
		return nil, err
	}

	result := fernet.VerifyAndDecrypt([]byte(encryptedData), 0, []*fernet.Key{key})
	return result, nil
}
