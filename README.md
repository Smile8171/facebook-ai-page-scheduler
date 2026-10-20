# Facebook Page AI photo scheduler

Add source photos to `photos/` in this repository. GitHub Actions cycles through
them, asks Gemini to create a new variation for every post, uploads the edited
image to the Facebook Page, and schedules three posts daily for 7:00 AM, 1:10 PM, and 5:00 PM
India time.

## One-time setup

1. Create a GitHub repository and copy this folder's contents into its root.
2. Add your source images under `photos/` and push them to the repository.
   Supported formats: JPG, JPEG, PNG, BMP, GIF, TIF, and TIFF.
3. In the repository, open **Settings > Secrets and variables > Actions** and add:
   - `FB_PAGE_ID`
   - `FB_PAGE_ACCESS_TOKEN`
   - `GEMINI_API_KEY`
   - `GEMINI_API_KEY_2` (optional backup key used when the first key is quota-limited)
   - `GEMINI_API_KEY_3` (optional additional fallback key)
4. Enable GitHub Actions and allow read/write repository contents under
   **Settings > Actions > General > Workflow permissions**.
5. Ensure the Meta app/Page token is authorized to create Page content. Meta
   requires a Page access token with `pages_manage_posts`,
   `pages_manage_engagement`, `pages_read_engagement`, and
   `pages_read_user_engagement`. The Page must grant the account the
   `CREATE_CONTENT`, `MANAGE`, and `MODERATE` tasks. Generate a fresh Page token
   after granting the permissions and save that token in GitHub Secrets.

GitHub Actions runs daily at 6:00 AM, 12:10 PM, and 4:00 PM India time
(00:30, 06:40, and 10:30 UTC), scheduling posts one hour later for 7:00 AM,
1:10 PM, and 5:00 PM. Each time slot is tracked separately in `state.json`,
so all three posts can be scheduled on the same date and reruns do not duplicate
a slot. If a run starts too late for the
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
- Gemini cycles through seven visual directions. Add `GEMINI_API_KEY_2` and `GEMINI_API_KEY_3` as optional fallback keys. The
  scheduler tries configured keys in order, switching when a key fails. Keep all
  keys in GitHub Secrets; do not put them in repository files.
  Review generated images for accuracy before enabling automatic publishing.
- The daily workflow requires a valid Gemini API key in `GEMINI_API_KEY`. Gemini
  availability, quotas, and charges depend on the Google account and model. The
  daily scheduler uses a 60-second HTTPX timeout per request and up to two
  attempts per configured key for photo editing. If editing fails, it makes one
  original-image generation attempt per configured key, using a randomly chosen
  fashion portrait prompt featuring a fictional adult Korean woman in a tasteful,
  non-explicit style. If Gemini generation fails for every configured key, it then requests an original portrait from Pollinations using the public image endpoint. If Pollinations also fails, it logs the error and uses a local Pillow edit of the source photo. The demo workflow still requires Gemini to succeed. Daily and demo scheduler steps are capped at 9 and 6 minutes,
  respectively; both jobs are capped at 10 minutes.
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
