# RustChain GitHub Tip Bot

A GitHub bot that allows users to tip RTC (RustChain tokens) directly in GitHub Issues and Pull Requests.

## Bounty

- **Reward:** 25-40 RTC
- **Issue:** [#1153](https://github.com/Scottcjn/rustchain-bounties/issues/1153)

## Features

### Required (25 RTC)
- `/tip @username AMOUNT RTC [memo]` - Send RTC to a user
- Validates sender is repo admin/maintainer
- Validates recipient has registered wallet
- Queues transfer via RustChain `/wallet/transfer` API
- Posts confirmation comment

### Bonus (40 RTC)
- `/balance` - Check your RTC balance
- `/leaderboard` - Top tipped contributors this month
- `/register WALLET_NAME` - Register your wallet
- Daily digest of all tips in a repo

## How It Works

1. User posts a comment with `/tip @username 5 RTC Great PR!`
2. Bot validates:
   - Sender has permission (repo admin/maintainer)
   - Recipient has registered their wallet
   - Rate limit check (10 tips/hour)
3. Bot queues the transfer via RustChain API
4. Bot posts confirmation with tx details

## Installation

### Option 1: GitHub Action (Recommended)

Add this workflow to your repository:

```yaml
name: RustChain Tip Bot
on: [issue_comment, pull_request_review_comment]
jobs:
  tip-bot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v7
        with:
          script: |
            // Bot implementation here
```

### Option 2: GitHub App

For more features, deploy as a GitHub App:
1. Create a GitHub App in your org settings
2. Subscribe to `issue_comment` and `pull_request_review_comment` events
3. Deploy the bot server (see `tip_bot.py`)

## Commands

| Command | Description |
|---------|-------------|
| `/tip @user AMOUNT RTC [memo]` | Send RTC to a user |
| `/balance` | Check your RTC balance |
| `/leaderboard` | Top tipped contributors |
| `/register WALLET_NAME` | Register your wallet |

## API Reference

### RustChain Node

```bash
# Check balance
curl -sk "https://50.28.86.131/wallet/balance?miner_id=WALLET_NAME"

# Transfer RTC
curl -sk -X POST https://50.28.86.131/wallet/transfer \
  -H 'Content-Type: application/json' \
  -d '{"from_wallet":"sender","to_wallet":"recipient","amount":5,"memo":"tip"}'
```

## Configuration

Environment variables:
- `RUSTCHAIN_NODE` - RustChain node URL (default: https://50.28.86.131)
- `GITHUB_TOKEN` - GitHub API token
- `ADMIN_KEY` - Admin key for transfers

## Demo

![Tip Bot Demo](demo.png)

## License

MIT
