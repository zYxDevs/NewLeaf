# NewLeaf

## Navigation

- [Project hub][hub]
- [Announcements][announce]
- [CloudTube repo][cloudtube]
- › NewLeaf repo
- [Documentation repo][docs]
- [Mailing list][list] for development and discussion
- [Todo tracker][todo] for listing problems and feature requests
- [Chatroom on Matrix][matrix]

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

[hub]: https://sr.ht/~cadence/tube/
[announce]: https://lists.sr.ht/~cadence/tube-announce
[cloudtube]: https://git.sr.ht/~cadence/cloudtube
[newleaf]: https://git.sr.ht/~cadence/NewLeaf
[list]: https://lists.sr.ht/~cadence/tube-devel
[todo]: https://todo.sr.ht/~cadence/tube
[matrix]: https://matrix.to/#/#cloudtube:cadence.moe
[docs]: https://git.sr.ht/~cadence/tube-docs
