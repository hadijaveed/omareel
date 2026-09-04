# Upload providers: setup and verification

A green configuration/readiness check means the destination is configured,
not that a cloud account was contacted. Use **Settings → Sharing → Test upload**
to verify that account.

## Start here: connect, test, share

1. Install `rclone` and `curl`: `sudo pacman -S rclone curl`.
2. Open **Omareel → Settings → Sharing** and choose your provider.
3. Fill in the fields using the matching guide below. Leave **Public URL**
   blank for a private bucket with a temporary signed video link.
4. Click **Save credentials**, then **Test upload**. A saved configuration
   alone is not proof that permissions or links work.
5. Make a short recording, **Stop & save**, then **Upload**. Open the resulting
   link in a signed-out browser. Check sound, picture, and seeking.

Keep **Upload every recording** off until this works. Omareel does not create
buckets or make them public for you. Do not paste secrets into an issue,
screenshot, chat, or the README.

### AWS S3

1. Create a bucket and note its region, for example `us-east-1`.
2. Create dedicated, restricted credentials for that bucket/folder. Use IAM
   access credentials, not your AWS root account keys. Allow object upload,
   readback and probe deletion; see the permissions section below.
3. In Omareel select **AWS S3**. Enter **Region**, **Bucket**, **Access key ID**
   and **Secret access key**. **Folder** is optional, for example `demos`.
4. For private sharing, leave **Public URL** blank. For persistent player
   pages, use a deliberately public object URL or CDN serving your bucket.
   The AWS console URL is not a Public URL.
5. Save credentials and run Test upload.

Temporary AWS session credentials and role-based authentication use an
**Existing rclone remote**, not this two-field credential form.

### Cloudflare R2

1. Create the bucket in **R2 Object Storage** and copy your account ID.
2. Generate bucket-scoped **Object Read & Write** credentials. Copy the
   generated **Access Key ID** and **Secret Access Key**. The Cloudflare API
   token string itself is not an S3 access key.
3. Choose **Cloudflare R2** in Omareel. Enter **Account ID**, **Bucket** and
   both keys. Region and the standard API endpoint are filled internally.
4. Leave Public URL blank for signed video links. For a permanent player
   page, connect your R2 custom domain and enter that URL. An enabled `r2.dev`
   development URL also works for testing; the S3 API endpoint is not a
   public website address.
5. Save credentials and run Test upload. Jurisdiction-specific endpoints
   need an Existing rclone remote.

### Backblaze B2

1. Create a B2 bucket. Find its S3 endpoint, for example
   `s3.us-west-005.backblazeb2.com`; the **Region** is `us-west-005`.
2. Create a bucket-restricted application key with upload, read and delete
   capabilities. Copy **keyID** and **applicationKey** immediately. Do not
   use the master application key for this S3 integration.
3. Choose **Backblaze B2**. Enter **Region**, **Bucket**, **Key ID** and
   **Application key** in their matching fields—do not swap them.
4. Leave Public URL blank for private signed video links. For a public
   bucket, use its friendly download base, such as
   `https://f005.backblazeb2.com/file/your-bucket`, or a configured CDN.
5. Save credentials and run Test upload.

### Another S3-compatible provider

Choose **S3-compatible**, enter the provider's HTTPS **API endpoint**, bucket,
keys and required region. Public URL is a separate browser-accessible base;
it is not necessarily the API endpoint. For custom addressing, session
tokens, encryption or provider-specific flags, configure rclone directly
and select **Existing rclone remote** instead.

### Existing rclone remote

Configure and verify the remote with `rclone config`, then enter
`remote-name:bucket-or-path` in Omareel. If supplying Public URL, include the
full mapped folder in that base. Otherwise the remote must support `rclone
link`; some backends do not. S3-compatible providers are the best-tested
sharing route; not every rclone backend can publish a browser-playable link.

### If Test upload fails

| Message or symptom | Check |
| --- | --- |
| Upload denied / 403 | Correct keys, bucket, region and write permission. |
| Uploaded object cannot be read | Read permission and correct endpoint/account. |
| Share URL inaccessible or wrong content | Public URL points to the actual object base, not a console/login page; check public access/CDN mapping. |
| Probe cleanup failed | Grant delete permission; remove only the exact temporary probe named in the error. |
| Playback link expires | Signed links are temporary; credentials/policies may expire earlier than seven days. Use deliberately public/CDN sharing for permanent links. |

Failed uploads keep the local video so you can correct settings and retry.

## Provider setup

| Provider | Configuration | Public sharing |
| --- | --- | --- |
| AWS S3 | Bucket region and access-key/secret pair. Omareel selects rclone's AWS provider. | Public object/website URL or CDN serving the bucket root; otherwise a signed video URL. |
| Cloudflare R2 | 32-character account ID and the **S3 Access Key ID + Secret Access Key** generated for an Object Read & Write R2 token, not the API token string. Region is auto. | A bucket custom domain or enabled development URL. The S3 API endpoint is not a public bucket URL. Otherwise a signed video URL. |
| Backblaze B2 | Application keyID + applicationKey and region from the bucket's S3 endpoint. B2's S3 API does not support the master application key. | Bucket friendly URL, such as https://f005.backblazeb2.com/file/bucket-name, or a CDN; otherwise a signed video URL. |
| S3-compatible | HTTPS endpoint, bucket, access-key/secret and service-specific region if required. | URL that serves the bucket's objects, or signed links if supported. |
| Existing rclone remote | A configured name:path. rclone manages OAuth and advanced settings. Environment-defined remotes and unlocked encrypted configurations also work. | Public URL mapped to the complete path, or the backend's link facility. Some backends cannot create share links. |

Use an **Existing rclone remote** for R2 jurisdiction-specific endpoints, AWS
temporary session credentials, special addressing/encryption requirements or
other advanced options. The basic credential form does not expose every option.
Saving a different provider/account/region requires its credential pair;
unrelated remotes are preserved. Use current rclone (tested with 1.75.0).

Sources: [Cloudflare setup](https://developers.cloudflare.com/r2/examples/rclone/),
[Backblaze S3 API](https://www.backblaze.com/apidocs/introduction-to-the-s3-compatible-api),
[rclone provider options](https://rclone.org/s3/).

## Permissions and link lifetime

Create the bucket first. Omareel sets no canned ACL and never changes bucket
policies. Allow object writes and reads in the chosen folder, plus deletion of
the probe. AWS multipart recovery can additionally require AbortMultipartUpload.
Account/bucket restrictions, KMS permissions and lifecycle rules still apply.

For public player pages, the public/CDN URL must serve HTML, MP4 and JPEG.
Use a dedicated sharing bucket or folder; do not expose unrelated private files.
Without Public URL, Omareel returns the provider's video/share link instead of
publishing HTML containing an expiring signed link. S3 links request seven days,
but credentials or policies can shorten that lifetime. Other backends may
return non-expiring links.

Sources: [S3 permissions](https://rclone.org/s3/#s3-permissions),
[AWS signed-URL expiry](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html),
[rclone link behavior](https://rclone.org/commands/rclone_link/).

## Folder mapping

With bucket recordings, Folder team/demos and Public URL https://video.example,
the object is omareel:recordings/team/demos/ID.mp4 and the URL is
https://video.example/team/demos/ID.mp4. Do not repeat the Folder in Public URL.
For Existing remote, its public URL must already include the full path.

Public URL must be a base URL without query parameters, user/password or
fragments—not a pre-signed object URL. Renaming an already shared take will
not rewrite its page into a different selected destination.

## Automated coverage

Run from the repository:

    python3 tests/upload-regression.py
    python3 tests/workflow-regression.py
    node tests/helpers.js

Configuration tests cover all four provider modes, required fields, credential
pairing/provider switches, unrelated remotes, 0600 atomic credential writes,
non-secret status, existing remotes, prefix/Unicode URLs, upload locking and
mid-upload settings changes.

Failure tests cover incorrect public content despite HTTP success, empty/failed
share links, deletion failures, thumbnail failure, player-page fallback and
preserving old links after switching destinations.

Integration uses a loopback-only, certificate-verified HTTPS S3 server and
dummy credentials. All four provider modes exercise real rclone uploads,
byte-for-byte read-back, signed links, deletion, multipart transfers, video
content type, inline/cache headers and byte-range data. Public player pages,
JPEG thumbnails and Existing remote paths are tested too.

This is **not live AWS/R2/B2 account certification**. The rclone 1.75 test server
returns a whole-file MD5 instead of AWS multipart ETags, and 200 rather than
206 for partial GETs. Tests adapt only the local client's ETag expectation and
independently check exact full/range bytes. Production checksum behavior is
unchanged. Metadata is checked on the upload server because this emulator
stores it in memory, not across processes.

## Final live-account acceptance

1. Save the intended credentials and run Test upload. Upload, read-back, share
   access and cleanup must pass. Cleanup failure names the unique probe that
   may remain; it never deletes an existing recording.
2. Share a short, non-sensitive recording and open it signed out. Check picture,
   sound, seeking and poster/player if enabled.
3. Test a recording larger than 200 MiB for the provider's normal multipart
   path. Check duration and seeking.
4. Check intended signed-link expiry, or public/CDN access and caching.

Actual account permissions, OAuth consent, custom domains, CDNs, outages,
expiring credentials and browser playback cannot be certified locally. These
checks close that remaining gap without risking private recordings.
