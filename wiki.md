# osu!Skill Wiki

Complete documentation on how osu!Skill analyzes your gameplay and what all the numbers mean.

## Overview

### What is osu!Skill?

osu!Skill is a comprehensive skill analysis system that goes beyond the traditional PP (Performance Points) system. It analyzes your recent gameplay against your peak performance to determine your current skill level and consistency.

**Key Philosophy:** Your skill is measured by how well you're currently performing compared to your peak ability, not just your highest PP scores.

The system uses three main components: **Recent Skill** (your current performance), **Peak Skill** (your best historical performance), and **Skill Match** (how close you are to your peak).

### Quick Start Guide

1. **Check Your Profile** - Log in with your osu! account to see your current skill analysis.
2. **Understand Your Verdict** - Your verdict tells you how well you're performing compared to your peak.
3. **Review Insights** - Get personalized recommendations based on your play patterns.

## Core Metrics

### Recent Skill
Measures your current skill level based on your recent plays (up to 30, only from the last 24 hours). This considers accuracy, star rating, mods, and temporal decay to emphasize newer plays.

**Range:** 0-200+ (higher is better)

### Peak Skill
Measures your historical peak performance based on your top 25 plays by PP. This represents what you're capable of at your best.

**Range:** 0-200+ (higher is better)

### Skill Match
The percentage of your peak skill that you're currently maintaining. This is the primary indicator of your current form.

**Formula:** `(Recent Skill / Peak Skill) × 100 × Reliability Factor`

**Range:** 0-100% (higher means closer to peak)

### Confidence
Indicates how reliable the analysis is based on data quality, play volume, diversity, and consistency.

**Range:** 0-100% (50%+ recommended)

## Verdicts Explained

### Accurate (92%+)
You're performing at or very close to your peak skill level. Your current rank accurately reflects your ability.

### Slightly Rusty (75-91%)
You're performing slightly below your peak but still maintaining good form. Minor practice should restore peak performance.

### Rusty (55-74%)
Noticeable decline from peak performance. You may need more practice to return to your best form.

### Overranked (35-54%)
Significant gap between current and peak performance. Your rank may be inflated compared to current skill.

### Inactive (<35%)
Very low recent activity or performance well below peak. Extended practice needed to restore skill.

### Insufficient Data
Not enough recent plays or confidence too low for reliable analysis. Play more to get accurate results.

## Calculations

### Skill Components

Each play is broken down into three skill components:

- **Aim Skill (45% weight):** Based on star rating, AR (Approach Rate), and accuracy. Higher star ratings and AR values increase aim skill.
- **Speed Skill (35% weight):** Based on BPM and star rating. Faster maps and higher star ratings increase speed skill.
- **Accuracy Skill (20% weight):** Rewards precision, especially on harder maps. Accuracy above 90% is heavily weighted.

### Mod Multipliers

Different mods affect skill calculations:

**Single Mods:**
- HD: 1.06x
- HR: 1.12x
- DT/NC: 1.18x
- EZ: 0.88x
- HT: 0.82x
- FL: 1.15x

**Combinations (override single mods):**
- DTHRHD: 1.35x
- DTHR: 1.28x
- DTHD: 1.24x
- HRHD: 1.18x

### Temporal Decay

Older plays are weighted less to emphasize recent performance:

- ≤14 days: 1.0x
- 15-30 days: 0.95x
- 31-60 days: 0.85x
- 61-90 days: 0.75x
- 91-180 days: 0.6x
- >180 days: exponential decay

## Advanced Features

### Confidence System

Confidence indicates how reliable the analysis is. It's calculated from four factors:

#### Volume (35%)
Based on number of recent plays. More plays provide more data points for analysis.

**Best results:** 25+ plays

#### Diversity (25%)
Based on unique beatmaps played. Playing different maps prevents over-specialization.

**Best results:** 15+ unique maps

#### Recency (25%)
Based on how spread out your plays are across different calendar weeks.

**Best results:** 6+ different weeks

#### Consistency (15%)
Based on accuracy standard deviation. More consistent accuracy indicates stable skill.

**Best results:** <5% accuracy deviation

**Confidence Formula:** `(Volume × 0.35) + (Diversity × 0.25) + (Recency × 0.25) + (Consistency × 0.15)`

### Data Requirements

#### Minimum Data
- **Recent Plays:** 6 minimum, 30 maximum (used plays from the last 24 hours)
- **Top Plays:** 8 minimum, 25 maximum used
- **Confidence Threshold:** 20% minimum for basic analysis

#### Data Validation
Each play must have valid:
- Accuracy (0-100%)
- Star rating (0-12*)
- AR (0-11)
- BPM (30-600)
- Timestamp

## Limitations

**Important:** osu!Skill is a supplementary tool, not a replacement for official rankings.

### System Limitations
- **Data Dependency:** Requires sufficient recent play data for accurate analysis
- **Skill Aspects:** May not capture all skill nuances (reading, flow, etc.)
- **Mod Complexity:** Simplified mod multipliers may not reflect true difficulty
- **Map Variety:** Analysis quality depends on map diversity

### Best Practices
- Play regularly for accurate analysis
- Play diverse maps and difficulties
- Focus on improvement, not just the numbers
- Use insights to identify improvement areas
- Aim for 50%+ confidence for reliable results

---

© 2025 osu!Skill. Built for the osu! community with ❤️