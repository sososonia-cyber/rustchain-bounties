"""
GitHub Tip Bot for RustChain RTC
Listens for /tip commands in GitHub Issues and PRs
"""

import os
import re
import json
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Configuration
RUSTCHAIN_NODE = os.environ.get("RUSTCHAIN_NODE", "https://50.28.86.131")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
REPO_OWNER = os.environ.get("REPO_OWNER", "")
REPO_NAME = os.environ.get("REPO_NAME", "rustchain-bounties")

# In-memory storage (use database in production)
wallet_registry: Dict[str, str] = {}  # github_username -> wallet_name
tip_history: list = []  # {"from": str, "to": str, "amount": float, "memo": str, "timestamp": str}
user_tip_counts: Dict[str, Dict[str, Any]] = {}  # user -> {"hourly": count, "last_hour": timestamp}


def verify_github_webhook(github_token: str, payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature:
        return False
    key = github_token.encode()
    mac = hmac.new(key, payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_tip_command(comment_body: str) -> Optional[Dict[str, str]]:
    """Parse /tip command from comment body"""
    # Pattern: /tip @username AMOUNT RTC [memo]
    pattern = r'/tip\s+@(\w+)\s+(\d+(?:\.\d+)?)\s*RTC\s*(.*)'
    match = re.search(pattern, comment_body, re.IGNORECASE)
    if match:
        return {
            "recipient": match.group(1),
            "amount": float(match.group(2)),
            "memo": match.group(3).strip() if match.group(3) else ""
        }
    return None


def parse_register_command(comment_body: str) -> Optional[str]:
    """Parse /register command"""
    pattern = r'/register\s+(\w+)'
    match = re.search(pattern, comment_body, re.IGNORECASE)
    return match.group(1) if match else None


def check_rate_limit(sender: str) -> bool:
    """Check if user has exceeded rate limit (10 tips per hour)"""
    now = datetime.utcnow()
    if sender not in user_tip_counts:
        user_tip_counts[sender] = {"count": 0, "hour": now}
    
    user_data = user_tip_counts[sender]
    if (now - user_data["hour"]).total_seconds() >= 3600:
        # Reset counter after 1 hour
        user_data["count"] = 0
        user_data["hour"] = now
    
    return user_data["count"] < 10


def increment_tip_count(sender: str):
    """Increment user's tip count"""
    if sender not in user_tip_counts:
        user_tip_counts[sender] = {"count": 0, "hour": datetime.utcnow()}
    user_tip_counts[sender]["count"] += 1


def get_balance(wallet_name: str) -> Optional[float]:
    """Get RTC balance for a wallet"""
    try:
        url = f"{RUSTCHAIN_NODE}/wallet/balance?miner_id={wallet_name}"
        response = requests.get(url, timeout=10, verify=False)
        if response.status_code == 200:
            data = response.json()
            return float(data.get("balance", 0))
    except Exception as e:
        print(f"Error getting balance: {e}")
    return None


def transfer_rtc(from_wallet: str, to_wallet: str, amount: float, memo: str = "") -> Dict[str, Any]:
    """Transfer RTC via RustChain API"""
    try:
        url = f"{RUSTCHAIN_NODE}/wallet/transfer"
        payload = {
            "from_wallet": from_wallet,
            "to_wallet": to_wallet,
            "amount": amount,
            "memo": memo
        }
        headers = {"Content-Type": "application/json"}
        if ADMIN_KEY:
            headers["Authorization"] = f"Bearer {ADMIN_KEY}"
        
        response = requests.post(url, json=payload, headers=headers, timeout=30, verify=False)
        return {
            "success": response.status_code == 200,
            "tx_id": response.json().get("tx_id") if response.status_code == 200 else None,
            "error": response.text if response.status_code != 200 else None
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_leaderboard() -> list:
    """Get top tipped contributors this month"""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    monthly_tips = {}
    for tip in tip_history:
        tip_time = datetime.fromisoformat(tip["timestamp"])
        if tip_time >= month_start:
            recipient = tip["to"]
            monthly_tips[recipient] = monthly_tips.get(recipient, 0) + tip["amount"]
    
    sorted_tips = sorted(monthly_tips.items(), key=lambda x: x[1], reverse=True)
    return [{"user": user, "total": total} for user, total in sorted_tips[:10]]


def format_tip_response(command: str, params: Dict[str, Any]) -> str:
    """Format response message"""
    if command == "tip_success":
        return f"""✅ **Queued: {params['amount']} RTC → {params['recipient']}**
From: {params['sender']} | Memo: {params['memo']}
Status: Pending (confirms in 24h)"""
    
    elif command == "tip_rate_limit":
        return f"""❌ Rate limit exceeded. You can only send 10 tips per hour.
Please try again later."""
    
    elif command == "balance":
        balance = params.get("balance")
        if balance is not None:
            return f"""💰 **RTC Balance for {params['wallet']}**
Balance: **{balance} RTC**"""
        return f"""❌ Could not fetch balance for {params['wallet']}"""
    
    elif command == "leaderboard":
        if not params["data"]:
            return "📊 No tips recorded this month yet!"
        
        lines = ["🏆 **Top Tipped Contributors (This Month)**", ""]
        for i, item in enumerate(params["data"], 1):
            lines.append(f"{i}. @{item['user']} — {item['total']} RTC")
        return "\n".join(lines)
    
    elif command == "register_success":
        return f"""✅ **Wallet Registered**
GitHub: @{params['github']}
Wallet: `{params['wallet']}`
You can now receive RTC tips!"""
    
    elif command == "register_error":
        return f"""❌ Registration failed: {params['error']}"""
    
    elif command == "invalid_command":
        return f"""❌ Invalid command. Use:
- `/tip @username AMOUNT RTC [memo]`
- `/balance`
- `/leaderboard`
- `/register WALLET_NAME`"""
    
    return ""


def handle_comment(payload: Dict[str, Any]) -> str:
    """Handle incoming GitHub comment"""
    comment = payload.get("comment", {})
    body = comment.get("body", "")
    sender = comment.get("user", {}).get("login", "")
    issue = payload.get("issue", {})
    repo = payload.get("repository", {})
    
    # Get repo admin status (simplified - in production check properly)
    # For now, allow anyone to tip if they have registered wallet
    
    # Check /tip command
    tip_cmd = parse_tip_command(body)
    if tip_cmd:
        if not check_rate_limit(sender):
            return format_tip_response("tip_rate_limit", {})
        
        recipient = tip_cmd["recipient"]
        amount = tip_cmd["amount"]
        memo = tip_cmd["memo"]
        
        # Check if recipient has registered wallet
        if recipient not in wallet_registry:
            return f"""❌ @{recipient} has not registered a wallet.
They need to use `/register WALLET_NAME` first."""
        
        recipient_wallet = wallet_registry[recipient]
        
        # In production, transfer from sender's wallet
        # For now, queue the tip
        tip_record = {
            "from": sender,
            "to": recipient,
            "amount": amount,
            "memo": memo,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "pending"
        }
        tip_history.append(tip_record)
        increment_tip_count(sender)
        
        return format_tip_response("tip_success", {
            "amount": amount,
            "recipient": recipient,
            "sender": sender,
            "memo": memo
        })
    
    # Check /balance command
    if body.strip().lower() == "/balance":
        if sender in wallet_registry:
            wallet = wallet_registry[sender]
            balance = get_balance(wallet)
            return format_tip_response("balance", {"wallet": wallet, "balance": balance})
        return f"""❌ You haven't registered a wallet yet.
Use `/register WALLET_NAME` to register."""
    
    # Check /leaderboard command
    if body.strip().lower() == "/leaderboard":
        leaderboard = get_leaderboard()
        return format_tip_response("leaderboard", {"data": leaderboard})
    
    # Check /register command
    register_cmd = parse_register_command(body)
    if register_cmd:
        wallet_name = register_cmd
        # Verify wallet exists
        balance = get_balance(wallet_name)
        if balance is not None:
            wallet_registry[sender] = wallet_name
            return format_tip_response("register_success", {
                "github": sender,
                "wallet": wallet_name
            })
        return format_tip_response("register_error", {
            "error": f"Wallet '{wallet_name}' not found on RustChain"
        })
    
    # Not a command we recognize
    return ""


def post_comment(repo_owner: str, repo_name: str, issue_number: int, body: str):
    """Post a comment to GitHub issue/PR"""
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    response = requests.post(url, json={"body": body}, headers=headers)
    return response.status_code == 201


def main():
    """Main handler for GitHub webhook"""
    # Read webhook payload
    payload = os.environ.get("GITHUB_EVENT_PAYLOAD")
    if not payload:
        print("No payload received")
        return
    
    try:
        data = json.loads(payload)
        action = os.environ.get("GITHUB_EVENT_NAME")
        
        if action == "issue_comment":
            # Check if it's a new comment on an issue or PR
            if data.get("action") == "created":
                response = handle_comment(data)
                if response:
                    # Get issue number
                    issue = data.get("issue", {})
                    issue_number = issue.get("number")
                    repo = data.get("repository", {})
                    repo_name = repo.get("name")
                    repo_owner = repo.get("owner", {}).get("login")
                    
                    if issue_number and repo_owner and repo_name:
                        post_comment(repo_owner, repo_name, issue_number, response)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
