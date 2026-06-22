# Afa Memorizer — Streamlit Community Cloud

This is the cloud-ready edition of the Afa Memorizer.

## Repository structure

Keep these files and folders in the repository root:

```text
app.py
requirements.txt
data/
  afa_cards.csv
```

## Deploy

1. Create a GitHub repository.
2. Upload the contents of this folder.
3. In Streamlit Community Cloud, create an app from the repository.
4. Choose `app.py` as the entrypoint.
5. Deploy.

No API key or secrets are required.

## Progress on the cloud edition

Progress is private to the current Streamlit browser session. To preserve it:

1. Open **Dashboard**.
2. Click **Download progress backup**.
3. Save `afa_progress_backup.json`.
4. On a future visit, open **Dashboard** and restore that file.

This avoids relying on temporary cloud filesystem storage.
