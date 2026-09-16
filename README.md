# social-carousels — asset bridge for the cloud carousel-publisher routine

Private repo. Holds the carousel PDFs + a queue, so the cloud routine `social-carousel-publisher`
can host and post LinkedIn PDF ("document") carousels with the laptop off.

## How it works
- `queue.json` — one entry per carousel: slug, brand, channel_id (Buffer LinkedIn channel), wp_pub
  (WordPress media lane), title, caption, pdf/thumb paths, and `status` (`ready` -> `posted`).
- `pdfs/` — the rendered PDF + a cover thumbnail per carousel.
- `upload_media.py` — uploads a file to the WordPress media library and prints its public URL
  (creds from the routine environment: B2BID_WP_URL / B2BID_WP_USER / B2BID_WP_APP_PASSWORD).

## The cloud routine's job each run
For every `queue.json` entry with `status: "ready"`:
1. `python upload_media.py --file <pdf> --pub <wp_pub> --alt "<title>"` -> public PDF URL.
2. `python upload_media.py --file <thumb> --pub <wp_pub> --alt "<title> cover"` -> public thumbnail URL.
3. Buffer MCP `create_post`: channelId, text=caption, schedulingType="automatic",
   mode="customScheduled", dueAt=<next free business day 13:30 UTC, >=3 days after the last post on
   that channel>, summary="<short>", assets=[{document:{url:<pdf url>, thumbnailUrl:<thumb url>, title:<title>}}].
4. Fetch the post back; if `assets` is non-empty, set that entry's `status` to `posted` and record the
   Buffer post id + dueAt in a `notes` field. If assets is empty, DELETE the post and leave status `ready`.
5. Commit `queue.json` back to this repo so the next run does not re-post it.

## Adding a carousel
Drop `pdfs/<slug>.pdf` + `pdfs/<slug>__thumb.png`, add a `ready` entry to `queue.json`, push. The routine
does the rest on its next run.
