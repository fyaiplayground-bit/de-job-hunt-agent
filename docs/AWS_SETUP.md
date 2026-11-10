# AWS setup for the S3 backup (decision #44)

FL does these steps herself: Claude doesn't create accounts or handle passwords and keys. About 15-20 minutes. Until they are done, the backup is simply off and the daily run works as before.

**Use a personal email and a personal card. Never the work account.**

## 1. Account and root safety (about 8 minutes)

1. Sign up at aws.amazon.com with a personal email.
2. Console → your name (top right) → **Security credentials** → **Assign MFA device**. Use an authenticator app. From now on the root login is only for emergencies.
3. Note the **12-digit account ID** under your name (top right). Claude needs it, and it isn't secret.

## 2. A $1 budget alert (2 minutes)

Console → **Billing and Cost Management** → **Budgets** → **Create budget** → *Zero spend budget* or a monthly cost budget of **$1** → your email. The backup should cost about $0.07 a month at first, so a $1 alert means something is wrong.

## 3. The bucket (3 minutes)

Console → region **US West (Oregon) us-west-2** (top right) → **S3** → **Create bucket**:

- **AWS Region**: check it says **US West (Oregon) us-west-2**. The page often opens on us-east-1, and a bucket can't move region later
- Bucket type: **General purpose**
- Bucket namespace: **Global namespace**. The newer "Account Regional namespace" may name buckets differently, and this setup hasn't been tested with it
- Name: something unique, for example `jobhunt-backup-` plus a few random letters, lowercase
- Copy settings from an existing bucket: skip
- Object Ownership: **ACLs disabled (recommended)**
- **Block all public access**: leave it on (the default), all four boxes ticked
- Bucket Versioning: **Disable**. Each day already gets its own file name, and with versioning the 30-day expiry would keep hidden old versions that cost money until a second rule removes them
- Tags: skip
- Default encryption: leave **SSE-S3** (the default). Bucket Key only matters for KMS, so leave it as it is
- Advanced settings: leave Object Lock **off**, or the 30-day expiry can't delete old backups
- Create.

Then open the bucket → **Management** → **Create lifecycle rule**:

- Name `expire-daily`, **Limit the scope** with prefix `daily/`
- **Expire current versions of objects** after **30** days
- Create. Monthly copies (`monthly/`) are kept.

## 4. A user that can only use this bucket (4 minutes)

Console → **IAM** → **Users** → **Create user** → name `jobhunt-backup`, no console access → next → **Attach policies directly** → skip → create. Open the user → **Add permissions** → **Create inline policy** → **JSON**, paste this with your bucket name in both places, and save it as `jobhunt-backup-bucket`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
    }
  ]
}
```

It can list, read and write this one bucket. It can't delete anything or reach anything else, so even a leaked key can't erase the backups.

Then **Security credentials** → **Create access key** → *Application running outside AWS* → create. Keep this page open for the next step. Don't paste the key into the chat.

## 5. Put the key on this computer (2 minutes)

In a Windows terminal (PowerShell, or the Terminal panel in the Claude app; not Ubuntu/WSL, which keeps its own separate AWS settings that the project can't see), run this one command and answer its four questions: the two key values from step 4, `us-west-2`, and `json`:

```
aws configure --profile jobhunt-backup
```

The key goes into your user folder's `.aws` files, not into the project and not to Claude. Then close the AWS page.

## 6. Tell Claude

Send Claude the **bucket name** and the **12-digit account ID**. Claude adds them to `.env` with `AWS_PROFILE=jobhunt-backup`, runs one backup and a restore check, and shows you the result.
