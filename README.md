# Second

A Python web project that mirrors the Invidious API, passing all calls
directly to youtube-dl and reformatting the response to be compatible.

## Status

These endpoints are somewhat implemented:

- `/api/v1/videos/{id}`
- `/api/v1/channels/{ucid}`
- `/api/v1/channels/{ucid}/{part}`
- `/api/v1/channels/{part}/{ucid}`
- `/api/v1/search?q={search}`
- `/api/v1/search/suggestions?q={search}`
- `/api/v1/captions/{id}`
- `/vi/{id}/{file}`
- `/api/manifest/dash/id/{id}`

## The future

- Playlists
- Channel playlists
- Proxying video streams and ?local
- ...anything else?

## License

AGPL 3
