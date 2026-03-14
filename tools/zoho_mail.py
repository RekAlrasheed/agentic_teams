#!/usr/bin/env python3
"""
Zoho Mail CLI tool for Navaia AI agents.
Uses Zoho Mail REST API directly with OAuth2.

Usage:
  python tools/zoho_mail.py list [--limit 10]
  python tools/zoho_mail.py read <message_id>
  python tools/zoho_mail.py send --to "email" --subject "sub" --body "body"
  python tools/zoho_mail.py reply <message_id> --body "reply text"
  python tools/zoho_mail.py search --query "keyword"
  python tools/zoho_mail.py folders
"""

import argparse
import json
import os
import sys
import requests


def load_env():
    """Load .env file from project root."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    if key and key not in os.environ:
                        os.environ[key] = value


def get_config():
    """Get Zoho Mail config from environment."""
    required = ['ZOHO_CLIENT_ID', 'ZOHO_CLIENT_SECRET', 'ZOHO_REFRESH_TOKEN', 'ZOHO_ACCOUNT_ID']
    config = {}
    for key in required:
        val = os.environ.get(key)
        if not val:
            print(f"Error: {key} not set in .env or environment", file=sys.stderr)
            sys.exit(1)
        config[key] = val
    config['ZOHO_DOMAIN'] = os.environ.get('ZOHO_DOMAIN', 'accounts.zoho.com')
    return config


def get_access_token(config):
    """Get a fresh access token using refresh token."""
    r = requests.post(f"https://{config['ZOHO_DOMAIN']}/oauth/v2/token", data={
        'grant_type': 'refresh_token',
        'client_id': config['ZOHO_CLIENT_ID'],
        'client_secret': config['ZOHO_CLIENT_SECRET'],
        'refresh_token': config['ZOHO_REFRESH_TOKEN'],
    }, timeout=10)
    data = r.json()
    if 'access_token' not in data:
        print(f"Error getting access token: {data}", file=sys.stderr)
        sys.exit(1)
    return data['access_token']


def api_get(token, account_id, endpoint, params=None):
    """Make a GET request to Zoho Mail API."""
    headers = {'Authorization': f'Zoho-oauthtoken {token}'}
    url = f"https://mail.zoho.com/api/accounts/{account_id}/{endpoint}"
    r = requests.get(url, headers=headers, params=params, timeout=15)
    return r.json()


def api_post(token, account_id, endpoint, payload):
    """Make a POST request to Zoho Mail API."""
    headers = {
        'Authorization': f'Zoho-oauthtoken {token}',
        'Content-Type': 'application/json',
    }
    url = f"https://mail.zoho.com/api/accounts/{account_id}/{endpoint}"
    r = requests.post(url, headers=headers, json=payload, timeout=15)
    return r.json()


def cmd_folders(args, token, account_id):
    """List all folders."""
    data = api_get(token, account_id, 'folders')
    folders = data.get('data', [])
    print(f"{'Folder':<25} {'ID':<25} {'Unread'}")
    print("-" * 60)
    for f in folders:
        name = f.get('folderName', 'unknown')
        fid = f.get('folderId', '')
        unread = f.get('unreadCount', 0)
        print(f"{name:<25} {fid:<25} {unread}")


def cmd_list(args, token, account_id):
    """List emails in inbox."""
    # Get inbox folder ID
    folders_data = api_get(token, account_id, 'folders')
    inbox_id = None
    for f in folders_data.get('data', []):
        if f.get('folderName', '').upper() == 'INBOX':
            inbox_id = f.get('folderId')
            break

    if not inbox_id:
        print("Error: Could not find INBOX folder", file=sys.stderr)
        sys.exit(1)

    data = api_get(token, account_id, 'messages/view', {
        'folderId': inbox_id,
        'limit': args.limit,
    })
    emails = data.get('data', [])
    print(f"Found {len(emails)} emails:\n")
    for e in emails:
        msg_id = e.get('messageId', '')
        sender = e.get('fromAddress', 'unknown')
        subject = e.get('subject', '(no subject)')
        date = e.get('receivedTime', '')
        status = 'UNREAD' if e.get('status2', '') == '0' else 'read'
        print(f"  ID: {msg_id}")
        print(f"  From: {sender}")
        print(f"  Subject: {subject}")
        print(f"  Status: {status}")
        print()


def cmd_read(args, token, account_id):
    """Read a specific email."""
    # Get inbox folder ID
    folders_data = api_get(token, account_id, 'folders')
    inbox_id = None
    for f in folders_data.get('data', []):
        if f.get('folderName', '').upper() == 'INBOX':
            inbox_id = f.get('folderId')
            break

    if not inbox_id:
        print("Error: Could not find INBOX folder", file=sys.stderr)
        sys.exit(1)

    data = api_get(token, account_id, f'folders/{inbox_id}/messages/{args.message_id}/content')
    content = data.get('data', {})
    print(f"From: {content.get('fromAddress', 'unknown')}")
    print(f"To: {content.get('toAddress', 'unknown')}")
    print(f"Subject: {content.get('subject', '(no subject)')}")
    print(f"Date: {content.get('receivedTime', '')}")
    print(f"\n--- Body ---\n")
    print(content.get('content', '(empty)'))


def cmd_send(args, token, account_id):
    """Send a new email."""
    payload = {
        'fromAddress': 'info@navaia.sa',
        'toAddress': args.to,
        'subject': args.subject,
        'content': args.body,
        'askReceipt': 'no',
    }
    if args.cc:
        payload['ccAddress'] = args.cc
    if args.bcc:
        payload['bccAddress'] = args.bcc

    data = api_post(token, account_id, 'messages', payload)
    if data.get('status', {}).get('code') == 200:
        print(f"Email sent successfully to {args.to}")
    else:
        print(f"Error: {json.dumps(data, indent=2)}")


def cmd_reply(args, token, account_id):
    """Reply to an existing email."""
    # First read the original email to get details
    folders_data = api_get(token, account_id, 'folders')
    inbox_id = None
    for f in folders_data.get('data', []):
        if f.get('folderName', '').upper() == 'INBOX':
            inbox_id = f.get('folderId')
            break

    if not inbox_id:
        print("Error: Could not find INBOX folder", file=sys.stderr)
        sys.exit(1)

    # Get original message
    orig = api_get(token, account_id, f'folders/{inbox_id}/messages/{args.message_id}/content')
    orig_data = orig.get('data', {})

    payload = {
        'fromAddress': 'info@navaia.sa',
        'toAddress': orig_data.get('fromAddress', ''),
        'subject': f"Re: {orig_data.get('subject', '')}",
        'content': args.body,
        'inReplyTo': args.message_id,
        'askReceipt': 'no',
    }

    data = api_post(token, account_id, f'messages/{args.message_id}', payload)
    if data.get('status', {}).get('code') == 200:
        print(f"Reply sent successfully to {payload['toAddress']}")
    else:
        print(f"Error: {json.dumps(data, indent=2)}")


def cmd_search(args, token, account_id):
    """Search emails."""
    data = api_get(token, account_id, 'messages/search', {
        'searchKey': args.query,
        'limit': args.limit,
    })
    emails = data.get('data', [])
    print(f"Found {len(emails)} results for '{args.query}':\n")
    for e in emails:
        print(f"  ID: {e.get('messageId', '')}")
        print(f"  From: {e.get('fromAddress', 'unknown')}")
        print(f"  Subject: {e.get('subject', '(no subject)')}")
        print()


def cmd_draft(args, token, account_id):
    """Save an email as draft."""
    payload = {
        'fromAddress': 'info@navaia.sa',
        'toAddress': args.to,
        'subject': args.subject,
        'content': args.body,
        'mode': 'draft',
    }

    data = api_post(token, account_id, 'messages', payload)
    if data.get('status', {}).get('code') == 200:
        print(f"Draft saved successfully")
    else:
        print(f"Error: {json.dumps(data, indent=2)}")


def main():
    load_env()

    parser = argparse.ArgumentParser(description='Zoho Mail CLI for Navaia agents')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # folders
    subparsers.add_parser('folders', help='List all folders')

    # list
    p_list = subparsers.add_parser('list', help='List inbox emails')
    p_list.add_argument('--limit', type=int, default=10, help='Number of emails')

    # read
    p_read = subparsers.add_parser('read', help='Read an email')
    p_read.add_argument('message_id', help='Message ID')

    # send
    p_send = subparsers.add_parser('send', help='Send an email')
    p_send.add_argument('--to', required=True, help='Recipient')
    p_send.add_argument('--subject', required=True, help='Subject')
    p_send.add_argument('--body', required=True, help='Body (HTML supported)')
    p_send.add_argument('--cc', help='CC recipients')
    p_send.add_argument('--bcc', help='BCC recipients')

    # reply
    p_reply = subparsers.add_parser('reply', help='Reply to an email')
    p_reply.add_argument('message_id', help='Message ID to reply to')
    p_reply.add_argument('--body', required=True, help='Reply body')

    # search
    p_search = subparsers.add_parser('search', help='Search emails')
    p_search.add_argument('--query', required=True, help='Search query')
    p_search.add_argument('--limit', type=int, default=10, help='Max results')

    # draft
    p_draft = subparsers.add_parser('draft', help='Save a draft')
    p_draft.add_argument('--to', required=True, help='Recipient')
    p_draft.add_argument('--subject', required=True, help='Subject')
    p_draft.add_argument('--body', required=True, help='Body')

    args = parser.parse_args()
    config = get_config()
    token = get_access_token(config)
    account_id = config['ZOHO_ACCOUNT_ID']

    commands = {
        'folders': cmd_folders,
        'list': cmd_list,
        'read': cmd_read,
        'send': cmd_send,
        'reply': cmd_reply,
        'search': cmd_search,
        'draft': cmd_draft,
    }

    commands[args.command](args, token, account_id)


if __name__ == '__main__':
    main()
