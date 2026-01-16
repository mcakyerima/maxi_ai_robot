# 🛡️ Parental Controls & Safety Features Guide

## Overview

Maxi AI includes comprehensive parental control features to ensure safe, age-appropriate interactions for children ages 6-12. This guide explains all safety features and how to use the parent dashboard.

---

## 🔐 Parent Dashboard

### Accessing the Dashboard

**Method 1: Hidden Access (Kid-Safe)**
1. Go to the main menu
2. **Tap the robot face 5 times quickly** (within 3 seconds)
3. The robot will animate and redirect to dashboard
4. Enter your PIN code

**Method 2: Direct URL**
- Navigate to: `http://your-server-url/parent-dashboard`
- Enter your PIN code

### Default PIN
- **Default PIN:** `1234`
- **⚠️ IMPORTANT:** Change this in your `.env` file before deployment!
```env
PARENT_DASHBOARD_PIN=your_secure_pin_here
```

---

## 📊 Dashboard Features

### 1. Today's Statistics
Monitor daily usage at a glance:
- **Total Learning Time**: How long kids used Maxi today
- **Questions Asked**: Total number of interactions
- **Math Problems**: Number of math questions solved
- **Chat Questions**: Number of chat conversations

### 2. Learning Topics (Past 7 Days)
See what your kids are learning about:
- Most discussed topics automatically categorized
- Shows frequency of each topic
- Helps identify learning interests

### 3. Safety Events (Past 7 Days)
Review any content filtering events:
- **Input filters**: Inappropriate questions blocked
- **Output filters**: Sanitized LLM responses
- Timestamps and reasons for each filter

**Example Safety Event:**
```
INPUT: inappropriate_keyword:weapon
Timestamp: 2026-01-16 10:30:00
```

---

## 🛡️ Safety Features

### 1. Content Filtering

#### Input Filtering
Blocks inappropriate questions before processing:
- Violence & harmful content
- Inappropriate topics for kids
- Drugs & substances
- Profanity
- Dangerous activities

**Blocked Keywords Include:**
```python
Violence: kill, murder, weapon, gun, knife, bomb, hurt, fight
Inappropriate: sex, porn, nude, adult
Drugs: alcohol, beer, cigarette, smoke, drug
Profanity: stupid, idiot, hate, damn
Dangerous: steal, rob, cheat, hack
```

#### Output Filtering
Sanitizes LLM responses:
- Removes URLs and external links
- Filters inappropriate words
- Simplifies complex language
- Ensures age-appropriate content

**Fallback Responses:**
When content is blocked, kids hear friendly responses like:
- "That's not something I can help with. How about we learn something cool instead?"
- "Let's keep our conversations friendly and educational! Ask me about animals, space, or math!"

### 2. Rate Limiting

Encourages healthy usage patterns:
- **Maximum:** 60 questions per hour (~1 per minute)
- **Session limit:** 100 questions maximum
- **Gentle warnings** at 80% of limit

**Rate Limit Messages:**
- At 48 questions: "You're doing great! Just 12 more questions this hour, then we'll rest!"
- At 60 questions: "Let's slow down a bit! Take a 10-minute break, then we can keep learning!"

### 3. Session Timer & Break Reminders

Visual progress bar tracks learning time:
- **Green** (0-30 mins): Active learning
- **Yellow** (30-45 mins): Approaching break time
- **Red** (45-60 mins): Break recommended

**Break Reminders:**
- **30 minutes:** "Great job learning! Maybe take a quick 5-minute break?"
- **45 minutes:** "You've been learning a lot! Time to rest your eyes and stretch!"
- **60 minutes:** "Wow, an hour of learning! Let's take a real break now. Come back soon!"

### 4. Usage Tracking

All interactions are logged for parental review:
- Questions asked (with timestamps)
- Topics discussed
- Session durations
- Filtered content events

**Database Storage:**
```
context_memory.db
├── usage_sessions      (Session metadata)
├── daily_statistics    (Daily aggregates)
├── content_filters     (Safety events)
└── question_logs       (Question tracking)
```

---

## 🔧 Configuration

### Environment Variables

Add to your `.env` file:
```env
# Parent Dashboard PIN (4 digits recommended)
PARENT_DASHBOARD_PIN=1234

# Rate Limiting (optional - defaults shown)
MAX_QUESTIONS_PER_HOUR=60
MAX_QUESTIONS_PER_SESSION=100

# Session Timer Thresholds (minutes)
BREAK_REMINDER_30=true
BREAK_REMINDER_45=true
BREAK_REMINDER_60=true
```

### Customizing Content Filters

Edit `brain/safety/content_filter.py`:

**Add Custom Blocked Keywords:**
```python
INAPPROPRIATE_KEYWORDS = {
    'your_custom_keyword',
    'another_blocked_word',
    # ... existing keywords
}
```

**Add Custom Patterns:**
```python
INAPPROPRIATE_PATTERNS = [
    r'your_regex_pattern',
    # ... existing patterns
]
```

**Customize Fallback Responses:**
```python
FALLBACK_RESPONSES = [
    "Your custom friendly response!",
    # ... existing responses
]
```

---

## 📱 API Endpoints

### Authentication
```http
POST /api/parent-dashboard/verify-pin
Content-Type: application/json

{
  "pin": "1234"
}

Response: {"success": true/false}
```

### Today's Statistics
```http
GET /api/parent-dashboard/today-stats

Response: {
  "date": "2026-01-16",
  "total_sessions": 3,
  "total_questions": 47,
  "total_time_minutes": 83,
  "chat_questions": 35,
  "math_questions": 12
}
```

### Weekly Topics
```http
GET /api/parent-dashboard/weekly-topics

Response: {
  "topics": [
    {"topic": "Solar System", "count": 5},
    {"topic": "Mathematics", "count": 12}
  ]
}
```

### Safety Events
```http
GET /api/parent-dashboard/safety-events?days=7

Response: {
  "events": [
    {
      "timestamp": "2026-01-16T10:30:00",
      "filter_type": "input",
      "reason": "inappropriate_keyword:weapon"
    }
  ]
}
```

---

## 🚀 Best Practices

### 1. Before Deployment
- [ ] Change default PIN to something secure
- [ ] Test dashboard access
- [ ] Review filtered keywords for your context
- [ ] Configure break reminder thresholds

### 2. Regular Monitoring
- [ ] Check dashboard weekly
- [ ] Review safety events
- [ ] Monitor learning topics
- [ ] Track session durations

### 3. Communication with Kids
- Explain the break reminders are for their health
- Encourage diverse question topics
- Review learned topics together
- Celebrate learning milestones

### 4. Privacy & Data
- All data stored locally in SQLite
- No external tracking or analytics
- Data persists in `context_memory.db`
- Can be deleted manually if needed

---

## 🔍 Troubleshooting

### Dashboard Won't Load
1. Check `.env` file has `PARENT_DASHBOARD_PIN` set
2. Verify Flask blueprints registered in `ui/app.py`
3. Check browser console for errors
4. Ensure database file exists: `context_memory.db`

### PIN Not Working
1. Verify PIN in `.env` matches entered PIN
2. Check for extra spaces in `.env` file
3. Restart server after changing `.env`
4. Try default PIN: `1234`

### No Statistics Showing
1. Check database file exists
2. Verify tables created: `usage_sessions`, `daily_statistics`
3. Ensure kids have used Maxi recently
4. Check browser console for API errors

### Safety Filter Too Strict
1. Edit `brain/safety/content_filter.py`
2. Remove keywords from `INAPPROPRIATE_KEYWORDS`
3. Comment out restrictive patterns
4. Test with sample questions
5. Restart server

### Safety Filter Too Lenient
1. Add more keywords to `INAPPROPRIATE_KEYWORDS`
2. Add patterns to `INAPPROPRIATE_PATTERNS`
3. Lower `WARNING_THRESHOLD` in rate_limiter.py
4. Test thoroughly

---

## 📚 Technical Architecture

### Safety Module Structure
```
brain/safety/
├── __init__.py            # Package exports
├── content_filter.py      # Input/output filtering
├── rate_limiter.py        # Usage limits
└── usage_tracker.py       # Session tracking
```

### Integration Points
```python
# In groq_llm_handler.py
from brain.safety import filter_input, filter_output, check_rate_limit

# In math_gesture_handler.py
from brain.safety import check_rate_limit, log_question
```

### Database Schema
```sql
-- Usage tracking
CREATE TABLE usage_sessions (
    session_id TEXT PRIMARY KEY,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    mode TEXT,
    questions_count INTEGER,
    duration_minutes INTEGER
);

-- Daily statistics
CREATE TABLE daily_statistics (
    date DATE PRIMARY KEY,
    total_sessions INTEGER,
    total_questions INTEGER,
    total_time_minutes INTEGER,
    chat_questions INTEGER,
    math_questions INTEGER
);

-- Safety events
CREATE TABLE content_filters (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    timestamp TIMESTAMP,
    filter_type TEXT,
    filtered_content TEXT,
    reason TEXT
);
```

---

## 🎯 Future Enhancements

Planned safety features:
- [ ] Weekly email summaries for parents
- [ ] Screen time limits with auto-shutdown
- [ ] Custom vocabulary expansion tracking
- [ ] Learning progress reports
- [ ] Multiple PIN codes for multiple parents
- [ ] Content filter customization UI
- [ ] Export statistics to CSV
- [ ] Push notifications for safety events

---

## 📞 Support

For questions or issues:
1. Check this guide first
2. Review `ARCHITECTURE.md` for system overview
3. Check `CONTEXT_MANAGER_GUIDE.md` for memory system
4. Review `CLOUD_DEPLOYMENT_GUIDE.md` for deployment

---

## ✅ Quick Checklist

Before going live:
- [ ] Changed default PIN
- [ ] Tested dashboard access
- [ ] Reviewed safety keywords
- [ ] Tested break reminders
- [ ] Monitored test sessions
- [ ] Verified statistics tracking
- [ ] Checked safety event logging
- [ ] Explained features to kids
- [ ] Set up regular monitoring schedule

---

**Remember:** These safety features are designed to guide and protect, not restrict learning. Review regularly and adjust based on your family's needs!

🛡️ **Happy Safe Learning!** 🚀
