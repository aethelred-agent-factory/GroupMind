# GroupMind Bot Commands

## Overview
GroupMind provides 6 powerful commands to analyze and understand your Telegram group conversations.

## Commands

### 📌 `/start`
**Shows welcome message and bot capabilities**
- Displays what the bot can do
- One-time command when first adding bot to a group

Example:
```
/start
```

Response:
```
👋 Welcome to GroupMind!

I'm your intelligent group chat assistant. I'll help you:
📊 Summarize conversations
🧠 Generate insights from group discussions
⚡ Answer questions about recent chat topics

Use /help for available commands.
```

---

### 📊 `/summary`
**Get AI-powered summary of recent group discussions**
- Analyzes last 50 messages (24-hour window)
- Uses DeepSeek AI for intelligent summarization
- Extracts key topics, decisions, and insights
- Includes sentiment analysis

Example:
```
/summary
```

Response:
```
📊 GROUP SUMMARY - Last 24 hours

🎯 Key Topics:
- Project timeline and deadlines
- Budget allocation discussion
- Team hiring plans

🤝 Decisions Made:
- Approved Q4 budget increase
- Scheduled planning meeting for next week

😊 Sentiment: 73% positive

⚡ Action Items:
- Prepare hiring briefs (mentioned 3x)
- Schedule vendor demos (mentioned 2x)
```

---

### 🔥 `/trending`
**Show most discussed topics from the past 24 hours**
- Analyzes keyword frequency in recent messages
- Shows top 5 most mentioned topics
- Helps identify what the group is focused on

Example:
```
/trending
```

Response:
```
🔥 Trending Topics (24h)

1. launch - mentioned 12x
2. design - mentioned 8x
3. feedback - mentioned 7x
4. deadline - mentioned 6x
5. review - mentioned 5x
```

---

### 💭 `/sentiment`
**Analyze the overall mood and sentiment of the group**
- Breaks down message sentiment distribution
- Shows percentage of positive, neutral, negative messages
- Calculates overall group mood
- Useful for team health monitoring

Example:
```
/sentiment
```

Response:
```
💭 Group Sentiment (24h)

😊 Positive: 42/58 (72%)
😐 Neutral: 12/58 (21%)
😞 Negative: 4/58 (7%)

🟢 Overall: Positive
```

---

### ✅ `/actions`
**Extract action items and TODOs from recent conversations**
- Scans messages for action keywords (todo, need to, will do, must, etc.)
- Extracts up to 10 most recent action items
- Helps team track what needs to be done

Example:
```
/actions
```

Response:
```
✅ Action Items (8 found)

1. update the design system documentation
2. schedule the budget review meeting
3. send feedback to the design team
4. prepare the vendor comparison spreadsheet
5. post the job descriptions on linkedin
6. finalize the q4 roadmap
7. book the conference room for standup
8. send slides to the stakeholders
```

---

### 📈 `/stats`
**View group statistics and activity metrics**
- Shows total messages in past 24 hours
- Displays unique user count
- Group creation date (if available)
- Useful for understanding group activity

Example:
```
/stats
```

Response:
```
📈 Group Statistics (24h)

💬 Messages: 287
👥 Unique Users: 12
📅 Group Created: 2024-06-15
⏱️ Last Updated: Just now
```

---

### ❓ `/help`
**Display all available commands and how to use them**
- Lists all 7 commands
- Shows brief descriptions
- Displays how to use the bot

Example:
```
/help
```

---

## Usage Tips

### Best Practices
1. **Use `/summary` after important discussions** - Get AI insights on what was discussed
2. **Check `/sentiment` for team health** - Monitor group mood over time
3. **Use `/actions` before standup** - Get a quick list of what needs doing
4. **Review `/trending` weekly** - See what your team is focused on
5. **Run `/stats` to track engagement** - Monitor group activity patterns

### Command Frequency
- `/summary` - Best used once per meeting or discussion block (rate limited)
- `/sentiment` - Use daily to monitor team health
- `/trending` - Use weekly for planning sessions
- `/actions` - Use before standups or planning meetings
- `/stats` - Use as needed to track engagement

### Rate Limiting
- Commands are rate limited per user (10 requests/minute, 100/hour)
- If you hit the limit, wait a moment before trying again
- This prevents abuse and ensures fair access for all users

### Privacy
- The bot automatically filters sensitive information (emails, phone numbers)
- Messages are stored in a secure database with soft-deletion support
- Users can opt-out of message tracking (contact group admin)

---

## Pro Tips

### For Team Leads
```
# Morning routine
/stats              # Check engagement
/sentiment          # Monitor team mood
/trending           # See focus areas
/actions            # Tasks for today
```

### For Project Managers
```
# End of day
/summary            # Document decisions
/actions            # Extract TODOs
/sentiment          # Track team morale
```

### For Product Managers
```
# Weekly planning
/trending           # What's being discussed
/sentiment          # Overall alignment
/stats              # Engagement levels
/summary            # Key decisions made
```

---

## Troubleshooting

**"Rate limited" message?**
- You've sent too many requests recently
- Wait 1-2 minutes and try again

**"No recent messages found"?**
- The group doesn't have any messages in the past 24 hours
- Send a few messages and try the command again

**"AI service not configured"?**
- The bot's AI service is misconfigured
- Contact the group admin or bot maintainer

**Summary looks incomplete?**
- The bot looks at the last 50 messages only
- For larger groups, you may need to summarize more frequently

---

## Support & Feedback

Found a bug? Have a feature request?
- Create an issue on the project repository
- Or mention it to your group admin

---

**GroupMind: Making group conversations searchable, understandable, and actionable.** 🚀
