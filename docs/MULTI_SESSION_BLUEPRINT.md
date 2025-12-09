# Multi-Session Feature Blueprint

## Overview
Allow each logged-in user to create and manage **multiple WhatsApp sessions** instead of being limited to one session per account.

---

## Current State
- Each user can have **1 WhatsApp session**
- Session is linked to user via `WaSenderSession.user` (ForeignKey)
- Campaigns use a single session selected at send time

---

## Proposed Changes

### 1. Database Model Updates

#### `WaSenderSession` Model
- **No structural change needed** - already supports multiple sessions per user via ForeignKey
- Add new fields:
  - `is_default` (BooleanField) - Mark one session as default for quick selection
  - `session_name` (CharField) - User-friendly name (e.g., "Sales Team", "Support")
  - `daily_limit` (IntegerField) - Per-session daily message limit
  - `messages_sent_today` (IntegerField) - Track daily usage per session

#### New Model: `SessionGroup` (Optional)
```
SessionGroup:
  - user (ForeignKey to User)
  - name (CharField) - e.g., "Marketing Sessions"
  - sessions (ManyToMany to WaSenderSession)
```

---

### 2. UI/UX Changes

#### Dashboard (`/whatsappapi/`)
- Show **session cards grid** instead of single session
- Each card displays:
  - Session name & phone number
  - Status (Connected/Disconnected)
  - Messages sent today / daily limit
  - Quick actions (Connect, Disconnect, Delete)
- "Add New Session" button

#### Session Management Page (`/whatsappapi/sessions/`)
- List all user sessions in a table
- Columns: Name, Phone, Status, Created, Last Active, Actions
- Bulk actions: Delete selected, Disconnect all
- Session limit indicator (e.g., "3 of 5 sessions used")

#### Create Session Page (`/whatsappapi/create-session/`)
- Add "Session Name" field
- Add "Set as Default" checkbox
- Show remaining session slots

#### Send Campaign Page (`/whatsappapi/send-campaign/`)
- **Session selector dropdown** with all connected sessions
- Option to select multiple sessions for load balancing
- Show session health indicators (green/yellow/red)

---

### 3. Backend Logic Changes

#### Session Creation (`views.create_session`)
- Check user's session limit before creating
- Validate session name uniqueness per user
- Auto-generate session name if not provided

#### Campaign Sending (`views.send_campaign`)
- Support single or multiple session selection
- If multiple sessions selected:
  - Round-robin distribution of contacts
  - Fallback to next session if one fails
  - Track which session sent to which contact

#### Session Rotation Logic (New)
```python
def get_next_available_session(user, exclude_sessions=[]):
    """
    Get the next session for sending based on:
    1. Connection status (must be connected)
    2. Daily limit not reached
    3. Least recently used
    """
    sessions = WaSenderSession.objects.filter(
        user=user,
        is_active=True,
        messages_sent_today__lt=F('daily_limit')
    ).exclude(id__in=exclude_sessions)
    .order_by('last_used_at')
    
    return sessions.first()
```

#### Daily Reset Task
- Reset `messages_sent_today` to 0 at midnight
- Add to scheduled tasks

---

### 4. Subscription/Limits Integration

#### Session Limits by Plan
| Plan | Max Sessions | Daily Limit/Session |
|------|--------------|---------------------|
| Free | 1 | 100 |
| Basic | 3 | 500 |
| Pro | 5 | 1000 |
| Enterprise | 10 | Unlimited |

#### Check in Views
```python
def can_create_session(user):
    current_count = WaSenderSession.objects.filter(user=user).count()
    max_allowed = user.subscription.max_sessions
    return current_count < max_allowed
```

---

### 5. API Endpoints (New/Modified)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sessions/` | GET | List all user sessions |
| `/api/sessions/` | POST | Create new session |
| `/api/sessions/<id>/` | GET | Get session details |
| `/api/sessions/<id>/` | DELETE | Delete session |
| `/api/sessions/<id>/set-default/` | POST | Set as default |
| `/api/sessions/<id>/connect/` | POST | Connect session |
| `/api/sessions/<id>/disconnect/` | POST | Disconnect session |
| `/api/sessions/stats/` | GET | Get all sessions stats |

---

### 6. Webhook Handling

#### Current
- Webhook URL: `/whatsappapi/webhook/<user_id>/`
- Single session per user

#### Proposed
- Keep same URL structure (user-level webhooks)
- Identify session from `sessionId` in webhook payload
- Route to correct session based on WaSender session ID

---

### 7. Migration Plan

#### Phase 1: Database
1. Add new fields to `WaSenderSession`
2. Create migration
3. Set existing sessions as `is_default=True`

#### Phase 2: Backend
1. Update session creation logic
2. Add session limit checks
3. Update campaign sending for multi-session

#### Phase 3: Frontend
1. Update dashboard UI
2. Update session management page
3. Update send campaign form

#### Phase 4: Testing
1. Test with 2-3 sessions per user
2. Test session rotation
3. Test webhook routing
4. Load testing

---

### 8. Files to Modify

#### Models
- `whatsappapi/models.py` - Add new fields

#### Views
- `whatsappapi/views.py` - Update create_session, send_campaign
- Add new API views for session management

#### Templates
- `whatsappapi/templates/whatsappapi/dashboard.html`
- `whatsappapi/templates/whatsappapi/sessions.html`
- `whatsappapi/templates/whatsappapi/create_session.html`
- `whatsappapi/templates/whatsappapi/send_campaign.html`

#### Tasks
- `whatsappapi/tasks.py` - Add daily reset task

#### URLs
- `whatsappapi/urls.py` - Add new API endpoints

---

### 9. Security Considerations

- Validate session ownership on all operations
- Rate limit session creation (prevent abuse)
- Audit log for session actions
- Secure session switching in campaigns

---

### 10. Future Enhancements

- **Session Templates**: Pre-configured session settings
- **Session Analytics**: Per-session performance metrics
- **Session Sharing**: Share sessions between team members
- **Auto-Reconnect**: Automatic reconnection for disconnected sessions
- **Session Health Monitoring**: Alerts for unhealthy sessions

---

## Timeline Estimate

| Phase | Duration | Priority |
|-------|----------|----------|
| Database & Models | 1 day | High |
| Backend Logic | 2-3 days | High |
| Frontend UI | 2-3 days | High |
| Testing & QA | 1-2 days | High |
| **Total** | **6-9 days** | |

---

## Notes

- Start with basic multi-session (no rotation)
- Add rotation/load balancing in v2
- Consider WaSender API limits per session
- Monitor for rate limiting issues

---

*Document Created: December 8, 2025*
*Status: Planning/Draft*
