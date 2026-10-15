# ADR 0012: Status, posts and channels (M5)

Status: built 15/10/2026 (Jerry chose all four recommended options). Shorts (short videos) and calls follow as M5.1
and M5.2.

## Decisions

| Question | Decision |
|---|---|
| First part of M5 | Status + posts + channels (no new servers) |
| Who sees a status | People you have a one-to-one chat with, minus anyone you hide it from |
| Who can start a channel | Verified accounts (level 2+); the owner and admins post, followers read |
| Reactions | Likes and comments; posts, comments and channels can be reported |

## How it works

- **Status**: text on a colour, or a photo with a caption. Lasts 24 hours (`MCXUS_STATUS_HOURS`), then the worker
  deletes it and its photo. Status photos are stored privately (`MCXUS_STATUS_DIR`, a Docker volume) and served
  only to the people allowed to see them. The owner sees who viewed each one and can delete it early.
- **Posts**: text and/or up to 4 photos (metadata stripped, resized like listing photos), for everyone or only the
  people you chat with. Discover shows posts (public, your contacts', your channels') mixed with new listings,
  newest first, paged with `?before=`. "Following" shows channel and contacts' posts only. Posting on Discover
  needs level 1; 20 posts, 100 comments and 30 statuses a day.
- **Likes and comments**: one like per person; the writer or the post's author can delete a comment.
- **Channels**: unique @handle (3–30 letters, numbers, dashes), up to 5 per owner. The owner adds admins; channel
  posts reach followers' feeds; anyone can open a channel and follow it.
- **Reports**: posts, comments and channels, once per person. Three open reports hide a post or comment until a
  moderator decides (same rule as listings). The console's **Reports** page has a tab for them: remove (a
  channel is suspended, its posts disappear) or keep (reports dismissed). Every decision is in the staff log.

## Privacy

- Status, posts and comments are **not end-to-end encrypted** (chats still are). The app says so where people
  post. Status is deleted after 24 hours; posts stay until the author deletes them (deleted posts are kept hidden
  for moderation and records).
- Contacts are worked out from existing one-to-one chats; nothing new about who knows whom is collected.

## Known limits

- No notifications yet for likes and comments on your posts.
- "Nearby" on Discover is not built yet (Market's location filters cover listings).
- Shorts and calls are separate modules (M5.1, M5.2).
