# GitHub Webhook Manager

A robust backend service for managing GitHub webhooks, user authentication, and repository integration.

## Overview

GitHub Webhook Manager is a specialized FastAPI application that facilitates:

- GitHub OAuth authentication
- Automated webhook setup and management
- Repository event tracking
- User profile integration

The service acts as a bridge between GitHub's API and your custom deployment platform, providing real-time repository event processing.

## Architecture

```
┌─────────────────┐      ┌────────────────┐      ┌─────────────────┐
│                 │      │                │      │                 │
│  GitHub API     │◄────►│  Backend API   │◄────►│  Deployment     │
│                 │      │                │      │  Platform       │
└─────────────────┘      └────────────────┘      └─────────────────┘
                                 ▲
                                 │
                                 ▼
                          ┌────────────────┐
                          │                │
                          │  Database      │
                          │                │
                          └────────────────┘
```

## API Endpoints

### Authentication (`/auth`)

| Endpoint | Method | Description | Platform Integration |
|----------|--------|-------------|----------------------|
| `/auth/login` | GET | Initiates GitHub OAuth login flow | Provides authentication required for platform operations |
| `/auth/callback` | GET | Handles GitHub OAuth callback | Receives and processes GitHub tokens for platform access |

### User Management (`/user`)

| Endpoint | Method | Description | Platform Integration |
|----------|--------|-------------|----------------------|
| `/user/profile` | GET | Retrieves GitHub user profile | Creates user account in deployment platform |
| `/user/repos` | GET | Lists user's GitHub repositories | Provides repository choices for platform integration |

### Webhook Management (`/api`)

| Endpoint | Method | Description | Platform Integration |
|----------|--------|-------------|----------------------|
| `/api/repos/{owner}/{repo}/commits` | GET | Retrieves repository commits | Provides commit information for deployment tracking |
| `/api/repos/{owner}/{repo}/setup-webhook` | POST | Sets up repository webhook | Connects repository events to deployment platform |
| `/api/webhook` | POST | Receives GitHub webhook events | Triggers deployment platform workflows |

## Deployment Platform Integration

The backend serves as a critical component in the deployment platform architecture:

1. **Authentication Layer**: 
   - Securely handles GitHub authentication
   - Provides access tokens for repository operations
   - Maintains user sessions across platform components

2. **Event Processing Pipeline**:
   - Receives webhook events from GitHub
   - Processes and validates event payloads
   - Forwards relevant events to deployment triggers

3. **Repository Integration**:
   - Automatically configures repository webhooks
   - Tracks commit history for deployment references
   - Provides repository metadata for deployment context

4. **User Management**:
   - Creates and maintains user profiles
   - Maps GitHub identities to platform accounts
   - Manages repository access permissions

## Environment Configuration

The application requires the following environment variables:

```
CLIENT_ID=<github_oauth_client_id>
CLIENT_SECRET=<github_oauth_client_secret>
REDIRECT_URI=<oauth_callback_url>  # Must match GitHub OAuth App settings
FRONTEND_URL=<frontend_application_url>
WEBHOOK_URL=<webhook_callback_url>
DATABASE_URL=<database_connection_string>
PASSWORD=<default_user_password>
```

### OAuth Configuration

The `REDIRECT_URI` is critical for OAuth authentication and must be configured correctly:

1. **Local Development**:
   ```
   REDIRECT_URI=http://localhost:8000/auth/callback
   ```

2. **Production**:
   ```
   REDIRECT_URI=https://your-domain.com/auth/callback
   ```

⚠️ **Important**: 
- The `REDIRECT_URI` must exactly match the "Authorization callback URL" in your GitHub OAuth App settings
- Configure this in GitHub: Settings > Developer Settings > OAuth Apps > Your App > Authorization callback URL
- The URI must use the correct protocol (http/https) and include the `/auth/callback` path
- Common issues:
  - Mismatched protocols (http vs https)
  - Missing or extra trailing slashes
  - Incorrect port numbers
  - Different domains

### Database Configuration

## API Usage Examples

Here's how to interact with the API endpoints using curl commands:

### Authentication

**1. Initiate GitHub OAuth Login:**
```bash
curl -X GET http://localhost:8000/auth/login
```
**Response:**
```json
{
  "login_url": "https://github.com/login/oauth/authorize?client_id=your_client_id&redirect_uri=your_redirect_uri&scope=repo admin:repo_hook"
}
```
**Usage:** Navigate to the provided `login_url` in a browser to begin the GitHub OAuth flow.

**Note:** The `/auth/callback` endpoint is not called directly - GitHub redirects to it with a temporary code after user authorization.

### User Management

**1. Get User Profile:**
```bash
curl -X GET http://localhost:8000/user/profile \
  -H "Authorization: Bearer your_github_token"
```
**Response:**
```json
{
  "login": "username",
  "id": 12345,
  "name": "User Name",
  "email": "user@example.com",
  "avatar_url": "https://avatars.githubusercontent.com/u/12345",
  "public_repos": 10,
  "followers": 5,
  "following": 8
}
```

**2. List User Repositories:**
```bash
curl -X GET http://localhost:8000/user/repos \
  -H "Authorization: Bearer your_github_token"
```
**Response:**
```json
[
  {
    "id": 98765,
    "name": "repo-name",
    "full_name": "username/repo-name",
    "private": false,
    "html_url": "https://github.com/username/repo-name",
    "description": "Repository description",
    "fork": false,
    "created_at": "2023-01-15T12:30:45Z",
    "updated_at": "2023-03-20T18:45:30Z",
    "pushed_at": "2023-03-18T10:20:15Z"
  },
  // Additional repositories...
]
```

### Webhook Management

**1. Get Repository Commits:**
```bash
curl -X GET http://localhost:8000/api/repos/username/repo-name/commits \
  -H "Authorization: Bearer your_github_token"
```
**Response:**
```json
[
  {
    "sha": "commit_sha_hash",
    "commit": {
      "author": {
        "name": "Author Name",
        "email": "author@example.com",
        "date": "2023-03-15T14:25:36Z"
      },
      "message": "Commit message"
    },
    "stats": {
      "additions": 15,
      "deletions": 5,
      "total": 20
    },
    "files": [
      {
        "filename": "path/to/file.py",
        "additions": 10,
        "deletions": 3,
        "changes": 13
      }
    ]
  },
  // Additional commits...
]
```

**2. Set Up Repository Webhook:**
```bash
curl -X POST http://localhost:8000/api/repos/username/repo-name/setup-webhook \
  -H "Authorization: Bearer your_github_token"
```
**Response:**
```json
{
  "status": "success",
  "message": "Webhook created successfully",
  "hook_id": "12345678"
}
```

**3. Receive Webhook Events (For Testing Only):**

GitHub will send POST requests to your webhook URL. You can simulate a webhook payload with:

```bash
curl -X POST http://localhost:8000/api/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{
    "repository": {
      "full_name": "username/repo-name"
    },
    "commits": [
      {
        "id": "commit_sha",
        "message": "Commit message",
        "author": {
          "name": "Author Name",
          "email": "author@example.com"
        }
      }
    ]
  }'
```
**Response:**
```json
{
  "status": "success",
  "event_id": "2023-04-10T15:30:45.123456-push"
}
```

## API Authentication

All authenticated endpoints require a GitHub access token passed as a Bearer token in the Authorization header:

```bash
curl -X GET http://your-api-url/endpoint \
  -H "Authorization: Bearer your_github_token"
```

This token is obtained through the OAuth flow initiated by the `/auth/login` endpoint.

## Development Setup

1. Install dependencies:
   ```