# QUARK Backend

A FastAPI-based deployment automation service that handles GitHub webhooks and manages deployments with real-time monitoring capabilities.

## Features

- 🔐 Multiple authentication methods:
  - Email/password registration and login
  - GitHub OAuth integration
  - Account linking between GitHub and regular accounts
- 🪝 Automated webhook management
- 📦 Deployment automation
- 🔄 Zero-downtime deployments
- 🌍 Environment variable management
- 📊 Real-time monitoring via WebSockets:
  - Deployment logs streaming
  - API request/response logging
  - System metrics monitoring
- 🚀 Auto-deploy on push
- 📝 Comprehensive request logging
- 🔒 Secure environment variable handling
- 🎯 Branch-specific deployment configurations
- 🔍 Detailed deployment history

## Authentication System

QUARK supports multiple authentication methods that can work together seamlessly:

### Email/Password Authentication

Regular authentication using email and password:

```bash
# Register a new user
curl -X 'POST' \
  'http://localhost:8000/auth/register' \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "your_username",
    "email": "your_email@example.com",
    "password": "your_secure_password"
  }'

# Login with credentials
curl -X 'POST' \
  'http://localhost:8000/auth/login' \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "your_email@example.com",
    "password": "your_secure_password"
  }'
```

Both methods return a JWT token to use for subsequent requests:

```json
{
  "access_token": "your.jwt.token",
  "token_type": "bearer",
  "user": {
    "id": "user_id",
    "username": "your_username",
    "email": "your_email@example.com",
    "github_connected": false,
    "auth_type": "password"
  }
}
```

### GitHub OAuth Authentication

For seamless GitHub integration:

1. Redirect user to GitHub login: `GET /auth/github/login`
2. GitHub redirects back to: `GET /auth/github/callback`
3. System provides a JWT token linked to GitHub account

### Account Linking

Users with regular accounts can link to GitHub:

1. Authenticate with email/password
2. Visit: `GET /auth/link-github`
3. Complete GitHub OAuth flow
4. Account is now linked and can access GitHub resources

### Authentication Flow

1. Endpoints that require GitHub access will work automatically with:
   - GitHub OAuth authenticated users
   - Regular users with linked GitHub accounts
2. The system uses a middleware that:
   - Detects authentication type (JWT or GitHub)
   - Adds GitHub tokens where needed
   - Ensures proper access controls

## Getting Started

### Prerequisites

- Python 3.9+
- pip
- Git
- Docker (optional, for containerized deployments)
- SQLite (default) or PostgreSQL (optional)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/QUARK-backend.git
cd QUARK-backend
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables in `.env`:
```env
CLIENT_ID=your_github_oauth_client_id
CLIENT_SECRET=your_github_oauth_client_secret
REDIRECT_URI=http://localhost:8000/auth/github/callback
FRONTEND_URL=http://localhost:5173
WEBHOOK_URL=http://your-webhook-url
WEBHOOK_SECRET=your-webhook-secret
DATABASE_URL=sqlite:///./app.db
PASSWORD=your_default_password
JWT_SECRET=your_secure_jwt_secret
```

5. Run the application:
```bash
python main.py
```

## Docker Deployment

1. Build the Docker image:
```bash
docker build -t quark-backend .
```

2. Run the container:
```bash
docker run -d \
  -p 8000:8000 \
  --name quark-backend \
  --env-file .env \
  quark-backend
```

## Using the API

### Authentication

1. Register or login to get your JWT token
2. Include the token in all requests:
   ```bash
   curl -H "Authorization: Bearer your.jwt.token" http://localhost:8000/endpoint
   ```

### Testing in Swagger UI

1. Visit http://localhost:8000/docs
2. Click the "Authorize" button at the top right
3. Enter your JWT token (without "Bearer" prefix)
4. Click "Authorize" then "Close"
5. All API requests in Swagger UI will now include your token

## Deployment Configuration

### Creating a Deployment Configuration

Create deployment configurations with environment variables using the `/deploy/configs` endpoint:

```bash
curl -X 'POST' \
  'http://localhost:8000/deploy/configs' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
  "repo_id": 12345678,
  "repo_full_name": "username/repo-name",
  "branch": "main",
  "auto_deploy": true,
  "deploy_command": "./deploy.sh",
  "environment_variables": {
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
    "API_KEY": "your-api-key",
    "NODE_ENV": "production",
    "PORT": "3000",
    "DEBUG": "false"
  }
}'
```

The environment variables will be:
1. Added to the deployment process environment
2. Written to a `.env` file in the repository root
3. Securely stored and managed per deployment

## WebSocket Architecture

QUARK uses a direct WebSocket implementation that bypasses the standard authentication middleware to ensure reliable connections:

### Key Implementation Details

- WebSocket endpoints are mounted directly on the main FastAPI app (not through routers)
- Path structure follows `/ws/logs/{log_id}` pattern for consistency
- Special aggregate channel `/ws/logs/all` provides all log events in a single stream
- Optional token-based authentication via query parameter (`?token=your_jwt_token`)
- WebSocket connections are managed by the LogConnectionManager class
- Middleware automatically detects and exempts WebSocket routes from authentication middleware

### Data Broadcast System

- Log entries are automatically broadcast to multiple channels:
  - Path-specific channel (based on the API endpoint)
  - `all_logs` channel for all log entries
  - Legacy `all` channel for backward compatibility
- Each channel can have multiple connected clients
- Dead connections are automatically cleaned up

### Real-Time Monitoring

#### WebSocket Endpoints

1. Deployment Logs:
```javascript
const ws = new WebSocket(`ws://localhost:8000/deployments/${deploymentId}/logs?token=${yourToken}`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'log') {
        console.log('Log:', data.data);
    } else if (data.type === 'status') {
        console.log('Status:', data.status);
    }
};
```

2. Individual Logs Stream:
```javascript
// Authenticated version
const ws = new WebSocket(`ws://localhost:8000/ws/logs/${logId}?token=${yourToken}`);

// Or without authentication
const ws = new WebSocket(`ws://localhost:8000/ws/logs/${logId}`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('API Log:', data);
};
```

3. All Logs Stream:
```javascript
// Authenticated version
const ws = new WebSocket(`ws://localhost:8000/ws/logs/all?token=${yourToken}`);

// Or without authentication
const ws = new WebSocket(`ws://localhost:8000/ws/logs/all`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('API Log:', data);
};
```

> Note: WebSocket endpoints support optional authentication via a token query parameter. Authenticated connections may receive more detailed log information depending on the user's permissions.

#### REST API Endpoints

```bash
# Get deployment status
curl -X 'GET' \
  'http://localhost:8000/deployments/{deployment_id}' \
  -H 'Authorization: Bearer YOUR_TOKEN'

# List deployments
curl -X 'GET' \
  'http://localhost:8000/deployments?limit=10&offset=0' \
  -H 'Authorization: Bearer YOUR_TOKEN'

# Get API request logs
curl -X 'GET' \
  'http://localhost:8000/logs' \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
QUARK-backend/
├── app/
│   ├── database/        # Database models and CRUD operations
│   ├── deployment/      # Deployment engine and logic
│   ├── routes/         # API routes and handlers
│   │   ├── auth.py    # Authentication routes
│   │   ├── deployments.py # Deployment management
│   │   ├── logs.py    # Logging endpoints
│   │   ├── user.py    # User management
│   │   └── webhooks.py # GitHub webhook handling
│   ├── schemas/        # Pydantic models and schemas
│   ├── utils/          # Utility functions and middleware
│   │   └── middleware.py # Contains RequestLoggingMiddleware with WebSocket bypass
│   └── websockets/     # WebSocket managers and handlers
│       └── logs.py     # LogConnectionManager for real-time log streaming
├── logs/              # Application logs
├── tests/             # Test files
├── .env              # Environment variables
├── dockerfile        # Docker configuration
├── main.py          # Application entry point
└── requirements.txt  # Python dependencies
```

## Development

### Running Tests

```bash
pytest
```

### Local Development

1. Start the server in development mode:
```bash
uvicorn main:app --reload
```

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| CLIENT_ID | GitHub OAuth client ID | Yes | - |
| CLIENT_SECRET | GitHub OAuth client secret | Yes | - |
| REDIRECT_URI | OAuth callback URL | Yes | - |
| FRONTEND_URL | Frontend application URL | Yes | - |
| WEBHOOK_URL | Webhook endpoint URL | Yes | - |
| WEBHOOK_SECRET | GitHub webhook secret | Yes | - |
| DATABASE_URL | Database connection string | No | sqlite:///./app.db |
| PASSWORD | Default password | Yes | - |
| JWT_SECRET | Secure JWT secret | Yes | - |

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Security

- All sensitive data is stored securely using environment variables
- Webhook signatures are verified using HMAC
- OAuth2 with JWT for authentication
- WebSocket endpoints support optional token-based authentication
- RequestLoggingMiddleware intelligently bypasses WebSocket connections
- WebSocket endpoints are mounted directly on the main app for security isolation
- Path-based pattern matching for WebSocket routes (`/ws/*` or `*/ws/*`)
- Rate limiting on sensitive endpoints
- Input validation using Pydantic models
- SQL injection prevention with SQLAlchemy

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue in the GitHub repository or contact the maintainers.