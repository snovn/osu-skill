# osu!Skill

> Discover your true osu! skill beyond PP with smart analysis and leaderboard insight.
![osu!Skill Banner](https://osuskill.com/static/icons/preview.png)

## Live Site

**[https://osuskill.com](https://osuskill.com)**

---

## Project Structure

```txt
osu-skillcheck/
├── app/
│   ├── api/              # API logic (osu + skill)
│   ├── auth/             # OAuth login
│   ├── models/           # Supabase database
│   ├── routes/           # Flask routes
│   ├── static/           # CSS
│   └── templates/        # HTML templates
├── run.py                # App entry
├── requirements.txt      # Dependencies
└── README.md
```

---

## Setup

```bash
git clone https://github.com/yourusername/osu-skillcheck.git
cd osu-skillcheck
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Add a `.env` file:

```env
OSU_CLIENT_ID=your_osu_api_client_id
OSU_CLIENT_SECRET=your_osu_api_secret
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
```

Run the app:

```bash
python run.py
```

Visit: [http://localhost:5000](http://localhost:5000)

---

## How It Works

### Skill Analysis

* Based on your **top 25** and **recent 30** plays
* Each play scored by:

  * **Aim** (AR + Star Rating)
  * **Speed** (BPM + difficulty)
  * **Accuracy** (hit %)
* Mods affect score: DT, HR, HD, etc.
* Retry attempts are penalized
* Older plays decay in weight

### Confidence

* Reflects how accurate the skill estimate is
* Based on data consistency, diversity, and volume
* Higher confidence = better leaderboard accuracy

### Leaderboard

* Users ranked by:

  ```
  (recent_skill × 0.7 + peak_skill × 0.3) × (confidence / 100)
  ```
* Refresh your stats by logging in or reanalyzing

---

## Key Routes

| Route                           | Purpose                    |
| ------------------------------- | -------------------------- |
| `/login`                        | Login with osu!            |
| `/dashboard`                    | View your skill stats      |
| `/leaderboard`                  | Global skill rankings      |
| `/api/analyze/<username>`       | Get analysis result (JSON) |
| `/api/user/<username>/position` | Get leaderboard position   |

---

## License

MIT
