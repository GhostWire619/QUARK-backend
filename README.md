Below is an updated `README.md` tailored to the new TypeScript API client (`api/services.ts`), Axios configuration (`api/client.ts`), and the React `LoginPage` component you provided. This version reflects the updated endpoints, authentication flow, and webhook-related functionality.

---

# GitHub Webhook Client Integration with React TypeScript and Axios

This guide explains how to use Axios in a React TypeScript application to interact with a FastAPI backend that provides GitHub authentication, user profile management, repository data, commit tracking, and webhook functionality. The frontend leverages Material-UI (MUI) for styling and React Query for data fetching.

## Prerequisites

- Node.js and npm installed.
- A React TypeScript project set up (e.g., `npx create-react-app my-app --template typescript`).
- A running FastAPI backend with the routes described in this guide.

## Installation

1. **Install Dependencies**:
   Add Axios, React Query, React Router, and Material-UI to your project:

   ```bash
   npm install axios react-query react-router-dom @mui/material @emotion/react @emotion/styled
   npm install --save-dev @types/axios @types/react-router-dom
   ```

2. **Set Up Environment Variables**:
   Create a `.env` file in your project root:
   ```env
   REACT_APP_API_URL=http://localhost:8000
   ```
   Add `.env` to `.gitignore` to keep it secure.

## API Client Configuration

Create `src/api/client.ts` to configure Axios with authentication and error handling:

```typescript
import axios from "axios";

const API_URL = import.meta.env.REACT_APP_API_URL || "http://localhost:8000";

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

## TypeScript Interfaces

Define interfaces for API responses in `src/types/index.ts`:

```typescript
export interface User {
  login: string;
  id: number;
  avatar_url: string;
  html_url: string;
  name?: string;
  email?: string;
  [key: string]: any;
}

export interface Repository {
  id: number;
  name: string;
  full_name: string;
  owner: { login: string; id: number };
  [key: string]: any;
}

export interface RepositoryFile {
  name: string;
  path: string;
  sha: string;
  type: "file" | "dir";
  [key: string]: any;
}

export interface Commit {
  sha: string;
  commit: {
    author: { name: string; email: string; date: string };
    message: string;
  };
  author?: { login: string; id: number };
  [key: string]: any;
}

export interface WebhookEvent {
  id: string;
  type: string;
  repository: string;
  timestamp: string;
  payload: { [key: string]: any };
}

export interface RegisteredWebhook {
  id: string;
  repository: string;
  hook_id: string;
  hook_url: string;
  events: string[];
  created_at: string;
  last_synced: string;
}
```

## API Service Functions

Create `src/api/services.ts` with functions for interacting with the backend:

```typescript
import apiClient from "./client";
import {
  Repository,
  RepositoryFile,
  User,
  WebhookEvent,
  RegisteredWebhook,
  Commit,
} from "../types";

// Auth services
export const getLoginUrl = async (): Promise<string> => {
  const response = await apiClient.get("/auth/login");
  return response.data.login_url;
};

// User services
export const fetchUserProfile = async (): Promise<User> => {
  const response = await apiClient.get("/api/user/profile");
  return response.data;
};
export const getUserDetails = fetchUserProfile;

export const fetchUserRepositories = async (): Promise<Repository[]> => {
  const response = await apiClient.get("/api/user/repos");
  return response.data;
};
export const getRepositories = fetchUserRepositories;

// Repository services
export const fetchRepositoryContents = async (
  owner: string,
  repo: string,
  path: string = ""
): Promise<RepositoryFile[]> => {
  const response = await apiClient.get(
    `/api/repos/${owner}/${repo}/contents/${path}`
  );
  return response.data;
};

// Webhook services
export const fetchWebhookEvents = async (): Promise<WebhookEvent[]> => {
  const response = await apiClient.get("/api/webhook-events");
  return response.data;
};

export const setupRepositoryWebhook = async (
  owner: string,
  repo: string
): Promise<{ status: string; message: string; hook_id?: string }> => {
  const response = await apiClient.post(
    `/api/repos/${owner}/${repo}/setup-webhook`
  );
  return response.data;
};

export const getRepositoryWebhooks = async (
  owner: string,
  repo: string
): Promise<any[]> => {
  const response = await apiClient.get(`/api/repos/${owner}/${repo}/hooks`);
  return response.data;
};

export const getRegisteredWebhooks = async (): Promise<RegisteredWebhook[]> => {
  const response = await apiClient.get("/api/registered-webhooks");
  return response.data;
};

export const getRepositoryRegisteredWebhooks = async (
  repository: string
): Promise<RegisteredWebhook[]> => {
  const response = await apiClient.get(
    `/api/registered-webhooks/${repository}`
  );
  return response.data;
};

export const isRepositoryConnected = async (
  owner: string,
  repo: string
): Promise<boolean> => {
  try {
    const repository = `${owner}/${repo}`;
    const webhooks = await getRepositoryRegisteredWebhooks(repository);
    return webhooks.length > 0;
  } catch (error) {
    console.error(
      `Error checking if repository ${owner}/${repo} is connected:`,
      error
    );
    return false;
  }
};

// Commit services
export const fetchRepositoryCommits = async (
  owner: string,
  repo: string,
  page: number = 1,
  per_page: number = 10
): Promise<Commit[]> => {
  const response = await apiClient.get(`/api/repos/${owner}/${repo}/commits`, {
    params: { page, per_page },
  });
  return response.data;
};

export const getCommitDetails = async (
  owner: string,
  repo: string,
  sha: string
): Promise<Commit> => {
  const response = await apiClient.get(
    `/api/repos/${owner}/${repo}/commits/${sha}`
  );
  return response.data;
};

export const subscribeToCommitUpdates = (
  owner: string,
  repo: string,
  callback: (commit: Commit) => void
): (() => void) => {
  const eventSource = new EventSource(
    `/api/repos/${owner}/${repo}/commits/stream`
  );
  eventSource.onmessage = (event) => {
    const commit = JSON.parse(event.data) as Commit;
    callback(commit);
  };
  return () => eventSource.close();
};
```

## Usage in React Components

### 1. Login Page with OAuth

The `LoginPage` component handles GitHub OAuth login and callback processing:

```typescript
import React, { useEffect } from "react";
import {
  Box,
  Button,
  Typography,
  Container,
  Paper,
  useTheme,
} from "@mui/material";
import GitHubIcon from "@mui/icons-material/GitHub";
import WebhookIcon from "@mui/icons-material/Webhook";
import { useQuery } from "@tanstack/react-query";
import { getLoginUrl } from "../api/services";
import { useNavigate } from "react-router-dom";

const LoginPage: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { data: loginUrl, isLoading } = useQuery("loginUrl", getLoginUrl);

  useEffect(() => {
    const queryParams = new URLSearchParams(window.location.search);
    const token = queryParams.get("token");
    if (token) {
      localStorage.setItem("token", token);
      navigate("/dashboard");
    }
  }, [navigate]);

  const handleLogin = () => {
    if (loginUrl) window.location.href = loginUrl;
  };

  return (
    <Container maxWidth="md" sx={{ py: 8 }}>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
        }}
      >
        <Paper
          elevation={0}
          sx={{
            p: 6,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "divider",
            maxWidth: 600,
            width: "100%",
          }}
        >
          <WebhookIcon
            sx={{ fontSize: 80, mb: 2, color: theme.palette.primary.main }}
          />
          <Typography
            variant="h4"
            component="h1"
            gutterBottom
            fontWeight="bold"
          >
            GitHub Webhook App
          </Typography>
          <Typography
            variant="body1"
            color="text.secondary"
            paragraph
            sx={{ mb: 4 }}
          >
            Connect your GitHub repositories and manage webhooks seamlessly.
            Receive real-time updates when changes are pushed to your
            repositories.
          </Typography>
          <Button
            variant="contained"
            size="large"
            color="primary"
            startIcon={<GitHubIcon />}
            onClick={handleLogin}
            disabled={isLoading}
            sx={{ py: 1.5, px: 4, fontSize: "1rem" }}
          >
            Login with GitHub
          </Button>
          <Box sx={{ mt: 4 }}>
            <Typography variant="caption" color="text.secondary">
              By logging in, you grant this application permission to access
              your GitHub repositories and manage webhooks.
            </Typography>
          </Box>
        </Paper>
        <Box sx={{ mt: 4, display: "flex", justifyContent: "center", gap: 4 }}>
          <Box>
            <Typography variant="h6" gutterBottom>
              Instant Notifications
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Receive alerts when changes are pushed
            </Typography>
          </Box>
          <Box>
            <Typography variant="h6" gutterBottom>
              Seamless Integration
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Easy setup with GitHub
            </Typography>
          </Box>
          <Box>
            <Typography variant="h6" gutterBottom>
              Repository Insights
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Monitor activity across repos
            </Typography>
          </Box>
        </Box>
      </Box>
    </Container>
  );
};

export default LoginPage;
```

### 2. Fetch User Profile

```typescript
import React from "react";
import { useQuery } from "react-query";
import { fetchUserProfile } from "../api/services";
import { Typography } from "@mui/material";

const Profile: React.FC = () => {
  const { data: profile, isLoading } = useQuery(
    "userProfile",
    fetchUserProfile
  );

  if (isLoading) return <Typography>Loading...</Typography>;
  if (!profile) return <Typography>Error loading profile</Typography>;

  return (
    <div>
      <Typography variant="h5">{profile.name || profile.login}</Typography>
      <img src={profile.avatar_url} alt="Avatar" width={100} />
      <Typography>Email: {profile.email || "N/A"}</Typography>
    </div>
  );
};

export default Profile;
```

### 3. Fetch User Repositories

```typescript
import React from "react";
import { useQuery } from "react-query";
import { fetchUserRepositories } from "../api/services";
import { List, ListItem, ListItemText } from "@mui/material";

const Repos: React.FC = () => {
  const { data: repos, isLoading } = useQuery(
    "userRepos",
    fetchUserRepositories
  );

  if (isLoading) return <div>Loading...</div>;

  return (
    <List>
      {repos?.map((repo) => (
        <ListItem key={repo.id}>
          <ListItemText primary={repo.full_name} />
        </ListItem>
      ))}
    </List>
  );
};

export default Repos;
```

### 4. Setup Webhook

```typescript
import React from "react";
import { useMutation } from "react-query";
import { setupRepositoryWebhook } from "../api/services";
import { Button, Typography } from "@mui/material";

const SetupWebhookButton: React.FC<{ owner: string; repo: string }> = ({
  owner,
  repo,
}) => {
  const mutation = useMutation(() => setupRepositoryWebhook(owner, repo));

  const handleSetup = () => mutation.mutate();

  return (
    <div>
      <Button onClick={handleSetup} disabled={mutation.isLoading}>
        Setup Webhook
      </Button>
      {mutation.data && (
        <Typography>
          {mutation.data.status}: {mutation.data.message}{" "}
          {mutation.data.hook_id && `(Hook ID: ${mutation.data.hook_id})`}
        </Typography>
      )}
    </div>
  );
};

export default SetupWebhookButton;
```

### 5. Subscribe to Commit Updates

```typescript
import React, { useEffect, useState } from "react";
import { subscribeToCommitUpdates } from "../api/services";
import { Typography } from "@mui/material";

const CommitStream: React.FC<{ owner: string; repo: string }> = ({
  owner,
  repo,
}) => {
  const [commits, setCommits] = useState<Commit[]>([]);

  useEffect(() => {
    const unsubscribe = subscribeToCommitUpdates(owner, repo, (commit) =>
      setCommits((prev) => [...prev, commit])
    );
    return unsubscribe; // Cleanup on unmount
  }, [owner, repo]);

  return (
    <div>
      <Typography variant="h6">Live Commit Updates</Typography>
      {commits.map((commit) => (
        <Typography key={commit.sha}>
          {commit.commit.message} - {commit.commit.author.name}
        </Typography>
      ))}
    </div>
  );
};

export default CommitStream;
```

## App Setup

Wrap your app with React Query and Router in `src/index.tsx`:

```typescript
import React from "react";
import ReactDOM from "react-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

const queryClient = new QueryClient();

ReactDOM.render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </QueryClientProvider>,
  document.getElementById("root")
);
```

Define routes in `src/App.tsx`:

```typescript
import React from "react";
import { Routes, Route } from "react-router-dom";
import LoginPage from "./components/LoginPage";
import Dashboard from "./components/Dashboard"; // Your dashboard component

const App: React.FC = () => (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/dashboard" element={<Dashboard />} />
    <Route path="/" element={<LoginPage />} />
  </Routes>
);

export default App;
```

## Notes

- **Authentication**: The token is stored in `localStorage` and attached to requests via the Axios interceptor.
- **Error Handling**: The interceptor redirects to `/login` on 401 errors.
- **Real-Time Updates**: The `subscribeToCommitUpdates` function uses Server-Sent Events (SSE); ensure your backend supports this endpoint.
- **Backend Routes**: Ensure the FastAPI backend implements all endpoints (e.g., `/api/webhook-events`, `/api/registered-webhooks`).

## Troubleshooting

- **401 Errors**: Verify the token is valid and the backend accepts it.
- **CORS**: Configure CORS in FastAPI to allow requests from your frontend URL.
- **SSE Issues**: Check if the `/commits/stream` endpoint is correctly implemented on the backend.

This README provides a complete guide to integrating your React TypeScript frontend with the FastAPI backend. Let me know if you need further details!
