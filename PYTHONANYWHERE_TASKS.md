# PythonAnywhere Tasks Configuration

## Overview
This document contains all the commands needed for PythonAnywhere scheduled and always-on tasks.

---

## Always-On Task (Required)

### Django-Q Worker
Processes background tasks like campaign sending.

```bash

cd /home/Abdul40/wa_campiagn_sender && /home/Abdul40/wa_campiagn_sender/venv/bin/python manage.py qcluster
```

**Setup:** Go to PythonAnywhere → Tasks → Always-On Tasks

---

## Scheduled Tasks

### 1. Check Stuck Campaigns
Automatically detects and resumes campaigns that got stuck (e.g., due to server restart).

```bash
/home/Abdul40/wa_campiagn_sender/venv/bin/python /home/Abdul40/wa_campiagn_sender/manage.py check_stuck_campaigns
```

**Recommended frequency:** Every 10 minutes

---

## Available Management Commands

| Command | Description |
|---------|-------------|
| `qcluster` | Django-Q worker for background tasks |
| `check_stuck_campaigns` | Auto-detect and resume stuck campaigns |
| `resume_stuck_campaigns` | Manually resume stuck campaigns |
| `check_openai_moderation` | Test OpenAI moderation API |
| `ai_moderation_scan` | Scan content with AI moderation |
| `ai_moderation_smoke` | Smoke test for AI moderation |

---

## Important Notes

1. **Always use full paths** - Don't use `cd &&` in PythonAnywhere scheduled tasks
2. **Use venv Python** - `/home/Abdul40/wa_campiagn_sender/venv/bin/python`
3. **Not system Python** - Don't use `python3.10` directly (missing packages)

---

## Database Commands (One-time setup)

### Enable Emoji Support (utf8mb4)
Run in MySQL console:

```sql
USE Abdul40$wa_campiagn_sender;
ALTER TABLE campaign_templates CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

## Deployment Checklist

1. ✅ Pull latest code: `cd ~/wa_campiagn_sender && git pull origin main`
2. ✅ Run migrations: `/home/Abdul40/wa_campiagn_sender/venv/bin/python /home/Abdul40/wa_campiagn_sender/manage.py migrate`
3. ✅ Reload web app from Web tab
4. ✅ Verify always-on task is running
5. ✅ Verify scheduled tasks are configured

---

*Last updated: December 9, 2025*
