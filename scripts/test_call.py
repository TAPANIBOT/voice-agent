#!/usr/bin/env python3
"""
Test script for Voice Agent

Usage:
    python scripts/test_call.py --to +358401234567
    python scripts/test_call.py --health
"""

import os
import sys
import argparse
import httpx

AGENT_URL = os.environ.get("VOICE_AGENT_URL", "http://localhost:8302")


def health_check():
    """Check if agent is running."""
    try:
        response = httpx.get(f"{AGENT_URL}/health", timeout=5.0)
        data = response.json()
        
        print(f"✅ Agent Status: {data.get('status')}")
        print(f"   Version: {data.get('version')}")
        print(f"   Active Calls: {data.get('active_calls')}")
        
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def start_call(to_number: str, greeting: str = None):
    """Start a test call."""
    if not greeting:
        greeting = "Hei! Tämä on Tapani, testipuhelu. Sano jotain niin vastaan."
    
    try:
        response = httpx.post(
            f"{AGENT_URL}/execute",
            json={
                "action": "start_call",
                "params": {
                    "to": to_number,
                    "greeting": greeting,
                    "context": "Test call"
                }
            },
            timeout=30.0
        )
        
        data = response.json()
        
        if data.get("success"):
            call_data = data.get("data", {})
            print(f"✅ Call started!")
            print(f"   Call ID: {call_data.get('call_id')}")
            print(f"   Status: {call_data.get('status')}")
            print(f"   To: {call_data.get('to')}")
            return call_data.get("call_id")
        else:
            error = data.get("error", {})
            print(f"❌ Call failed: {error.get('message')}")
            return None
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
        return None


def list_calls():
    """List active calls."""
    try:
        response = httpx.get(f"{AGENT_URL}/calls", timeout=5.0)
        data = response.json()
        
        calls = data.get("data", {}).get("calls", [])
        
        if not calls:
            print("📞 No active calls")
        else:
            print(f"📞 Active calls ({len(calls)}):")
            for call in calls:
                print(f"   - {call.get('call_id')[:20]}... ({call.get('status')})")
        
        return calls
    except Exception as e:
        print(f"❌ Failed: {e}")
        return []


def hangup_call(call_id: str):
    """Hang up a call."""
    try:
        response = httpx.post(
            f"{AGENT_URL}/execute",
            json={
                "action": "hangup",
                "params": {
                    "call_id": call_id,
                    "reason": "test_ended"
                }
            },
            timeout=10.0
        )
        
        data = response.json()
        
        if data.get("success"):
            print(f"✅ Call ended: {call_id[:20]}...")
        else:
            print(f"❌ Hangup failed: {data.get('error', {}).get('message')}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Voice Agent Test Script")
    parser.add_argument("--health", action="store_true", help="Health check")
    parser.add_argument("--to", type=str, help="Phone number to call (E.164)")
    parser.add_argument("--greeting", type=str, help="Custom greeting")
    parser.add_argument("--list", action="store_true", help="List active calls")
    parser.add_argument("--hangup", type=str, help="Hang up call by ID")
    
    args = parser.parse_args()
    
    if args.health:
        health_check()
    elif args.to:
        if not args.to.startswith("+"):
            print("❌ Phone number must be in E.164 format (+358...)")
            sys.exit(1)
        start_call(args.to, args.greeting)
    elif args.list:
        list_calls()
    elif args.hangup:
        hangup_call(args.hangup)
    else:
        # Default: health check
        health_check()


if __name__ == "__main__":
    main()
