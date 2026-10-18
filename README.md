# Facebook Page AI photo scheduler

Add photos to `photos/` in this repository. GitHub Actions will pick the next
unused photo, use Gemini to create an AI-edited variation, upload it to the
Facebook Page, and schedule it for 7:00 AM India time.

## One-time setup

1. Create a GitHub repository and copy this folder's contents into its root.
2. Add your source images under `photos/` and push them to the repository.
   Supported formats: JPG, JPEG, PNG, BMP, GIF, TIF, and TIFF.
3. In the repository, open **Settings → Secrets and variables → Actions** and add:
   - `FB_PAGE_ID`
   - `FB_PAGE_ACCESS_TOKEN`
   - `GEMINI_API_KEY`
4. Enable GitHub Actions and allow read/write repository contents under
   **Settings → Actions → General → Workflow permissions**.
5. Ensure the Meta app/Page token is authorized to create Page content. Meta
   requires a Page access token with `pages_manage_posts`,
   `pages_manage_engagement`, `pages_read_engagement`, and
   `pages_read_user_engagement`. The Page must grant the account the
   `CREATE_CONTENT`, `MANAGE`, and `MODERATE` tasks. Generate a fresh Page token
   after granting the permissions and save that token in GitHub Secrets.

GitHub Actions runs daily at 6:00 AM India time (00:30 UTC) to schedule the
Facebook post for 7:00 AM India time. A manual workflow run is safe: it will
not schedule a second post on a date already recorded in `state.json`. If the
scheduled workflow starts too late for Facebook's future-scheduling window,
the script chooses the next day's 7:00 AM slot.

## Add and manage photos

- Upload as many photos as you like into `photos/`. One unused photo is used
  per day, in alphabetical path order.
- Gemini cycles through seven visual directions and can alter pose, outfit, and
  background while trying to preserve the subject's recognizable identity.
  Review generated images for accuracy before enabling automatic publishing.
- The workflow requires a valid Gemini API key in `GEMINI_API_KEY`. Gemini
  availability, quotas, and any API charges depend on the Google account and
  model being used. If editing fails, the workflow stops rather than publishing
  the unedited source photo.
- Images with transparency are placed on a white background. Animated images
  use their first frame. Photos are converted to JPEG and resized to fit
  Facebook's image size limits without cropping.
- After a photo is processed, its path is recorded in `state.json`. Use a new
  filename when adding a replacement photo; renaming a photo makes it a new
  queue item.
- If there are no new photos, the workflow exits without publishing anything.
- To change the caption, set the optional repository variable
  `FB_POST_CAPTION`. The default is `Aaj ki nayi vibe!`.
- Set the optional repository variable `FB_GRAPH_API_VERSION` to a currently
  supported Graph API version; the default is `v26.0`.

## Costs and limitations

The workflow schedules content only for a Facebook Page you are authorized to
manage; it does not automate personal-profile logins. GitHub scheduled runs
can be delayed. Facebook's scheduled-post permissions, token validity, and
API availability are controlled by Meta. AI image edits may be imperfect and
do not guarantee exact poses, clothing, or scene details.

There is an unavoidable small retry risk if Facebook accepts the scheduled
post but the workflow fails before committing `state.json`. Check Page
scheduled content before manually retrying such a failed run.
