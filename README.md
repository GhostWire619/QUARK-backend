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
REDIRECT_URI=<oauth_callback_url>
FRONTEND_URL=<frontend_application_url>
WEBHOOK_URL=<webhook_callback_url>
DATABASE_URL=<database_connection_string>
PASSWORD=<default_user_password>
```

## Development Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Configure environment variables

3. Run the application:
   ```
   uvicorn main:app --reload
   ```

## Docker Deployment

The application includes a Dockerfile for containerized deployment:

```
docker build -t github-webhook-manager .
docker run -p 8000:8000 -e CLIENT_ID=xxx -e CLIENT_SECRET=xxx ... github-webhook-manager
```

## API Documentation

Interactive API documentation is available at:
- Swagger UI: `/docs`
- ReDoc: `/redoc`

## Webhook Event Flow

1. User authenticates with GitHub
2. Backend configures webhook on repository
3. GitHub sends events to webhook endpoint
4. Backend processes events and stores relevant data
5. Deployment platform receives processed events
6. Platform executes appropriate workflows based on events

## Security Considerations

- GitHub tokens are never stored persistently
- Webhook payloads are validated before processing
- User authentication is required for sensitive operations
- Repository access is limited to authenticated user's permissions
