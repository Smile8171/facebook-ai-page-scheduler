# Facebook Page AI photo scheduler

Add source photos to `photos/` in this repository. GitHub Actions cycles through
them, asks Gemini to create a new variation for every post, uploads the edited
image to the Facebook Page, and schedules two posts daily for 7:00 AM and
5:00 PM India time.

## One-time setup

1. Create a GitHub repository and copy this folder's contents into its root.
2. Add your source images under `photos/` and push them to the repository.
   Supported formats: JPG, JPEG, PNG, BMP, GIF, TIF, and TIFF.
3. In the repository, open **Settings > Secrets and variables > Actions** and add:
   - `FB_PAGE_ID`
   - `FB_PAGE_ACCESS_TOKEN`
   - `GEMINI_API_KEY`
   - `GEMINI_API_KEY_2` (optional backup key used when the first key is quota-limited)
4. Enable GitHub Actions and allow read/write repository contents under
   **Settings > Actions > General > Workflow permissions**.
5. Ensure the Meta app/Page token is authorized to create Page content. Meta
   requires a Page access token with `pages_manage_posts`,
   `pages_manage_engagement`, `pages_read_engagement`, and
   `pages_read_user_engagement`. The Page must grant the account the
   `CREATE_CONTENT`, `MANAGE`, and `MODERATE` tasks. Generate a fresh Page token
   after granting the permissions and save that token in GitHub Secrets.

GitHub Actions runs daily at 6:00 AM and 4:00 PM India time (00:30 and 10:30
UTC), scheduling posts one hour later for 7:00 AM and 5:00 PM. Each time slot is
tracked separately in `state.json`, so both posts can be scheduled on the same
date and reruns do not duplicate a slot. If a run starts too late for the
upcoming slot, the scheduler chooses the next available slot.

To publish one public demo immediately, manually run **Publish Gemini-edited
demo** from the Actions tab. It publishes a Gemini-edited image from the next
photo in the cycle. The demo is a real public post; delete it from Facebook if
you only wanted a preview.

## Add and manage photos

- Upload photos into `photos/`. They are used in alphabetical order and then
  cycled again, so the schedule keeps running after every source photo has been
  used. Each post sends the source photo to Gemini again and requests a visibly
  different pose, camera angle, outfit, and background while preserving the
  subject's recognizable identity.
- Gemini cycles through seven visual directions. Add `GEMINI_API_KEY_2` as a
  GitHub Actions secret to let the scheduler switch to the backup key when the
  first key reaches its quota. Keep both keys in GitHub Secrets; do not put
  them in repository files.
  Review generated images for accuracy before enabling automatic publishing.
- The workflow requires a valid Gemini API key in `GEMINI_API_KEY`. Gemini
  availability, quotas, and any API charges depend on the Google account and
  model being used. Each Gemini image request has a 60-second timeout and up to two application attempts per configured key. The scheduler step in both daily and demo workflows is capped at 6 minutes, and each job at 10 minutes; logs include sanitized SDK failure details and retry progress. If editing fails
  with both keys, the workflow stops rather than publishing the unedited source
  photo.
- Images with transparency are placed on a white background. Animated images
  use their first frame. Photos are converted to JPEG and resized to fit
  Facebook's image size limits without cropping.
- Each post's source path is recorded in `state.json`, including repeated
  cycles. Newly added photos join the alphabetical cycle.
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
