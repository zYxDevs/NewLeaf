# Second

A Python web project that mirrors the Invidious API, passing all calls
directly to youtube-dl and reformatting the response to be compatible.

## Status

These endpoints are somewhat implemented:

- `/api/v1/videos/{id}`
- `/api/v1/channels/{ucid}`
- `/api/v1/channels/{ucid}/{part}`
- `/api/v1/channels/{part}/{ucid}`

## The future

- Video recommendations
- RSS as a source for channel listings
- Searches
- Dash manifests
- Proxying video streams and ?local

## License

AGPL 3
