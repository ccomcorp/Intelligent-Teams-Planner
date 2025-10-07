# OAuth Setup and Testing Guide

## 🔧 Port Configuration: 8888

The OAuth callback server has been configured to use **port 8888** instead of the default 8000 to avoid conflicts with other development servers.

### Server Configuration

**OAuth Callback Server:**
- **URL:** `http://localhost:8888`
- **Callback Endpoint:** `http://localhost:8888/auth/callback`
- **Instructions Page:** `http://localhost:8888`

### Files Updated for Port 8888

1. **`src/auth.py`** - Default redirect URI updated
2. **`oauth_callback_server.py`** - Server configuration and documentation
3. **Documentation** - All references updated to port 8888

## 🚀 Quick Start Guide

### 1. Start the OAuth Callback Server
```bash
cd planner-mcp-server
python oauth_callback_server.py
```

Expected output:
```
🚀 Starting OAuth Callback Server...
📍 Server will be available at: http://localhost:8888
🔗 OAuth callback URL: http://localhost:8888/auth/callback
📋 Visit http://localhost:8888 for instructions

✅ Cache service initialized
✅ Auth service initialized
✅ Teams/Planner client initialized
INFO: Uvicorn running on http://0.0.0.0:8888
```

### 2. Generate OAuth URL
```bash
python mvp_test_cli.py
```

This will generate an OAuth URL that redirects to port 8888:
```
https://login.microsoftonline.com/.../oauth2/v2.0/authorize?...&redirect_uri=http%3A%2F%2Flocalhost%3A8888%2Fauth%2Fcallback&...
```

### 3. Complete Authentication Flow

1. **Copy the OAuth URL** from the CLI output
2. **Paste it in your browser** to visit Microsoft's authentication page
3. **Sign in with your Microsoft account** and grant permissions
4. **Get redirected to** `http://localhost:8888/auth/callback`
5. **View real-time test results** of Microsoft Graph API connectivity

## 🔍 Testing Results

The callback server will automatically test:

- ✅ **User Authentication** - Verify login and get user profile
- ✅ **Microsoft Teams Access** - List your teams
- ✅ **Microsoft Planner Access** - Get plans from your teams
- ✅ **Task Management** - Create a test task to verify write permissions
- 📊 **Comprehensive Results** - Display all test outcomes in a web page

## 🛠 Configuration Details

### Environment Variables Required
```env
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_TENANT_ID=your-tenant-id
ENCRYPTION_KEY=32-character-encryption-key
REDIS_URL=redis://localhost:6379/0
```

### Microsoft Graph Scopes
The application requests these essential scopes:
- `User.Read` - Read user profile information
- `Group.Read.All` - Read Microsoft Teams (groups)
- `Group.ReadWrite.All` - Full access to Teams and Planner
- `Tasks.Read` - Read Planner tasks
- `Tasks.ReadWrite` - Create/update Planner tasks

### Azure App Registration Requirements
In your Azure App Registration, ensure:
1. **Redirect URI** is set to: `http://localhost:8888/auth/callback`
2. **API Permissions** include all the scopes listed above
3. **Platform** is configured for "Web" applications

## 🔧 Troubleshooting

### Common Issues

**Port Already in Use:**
```bash
# Check what's using port 8888
lsof -i :8888

# Kill any conflicting process
pkill -f "port.*8888"
```

**OAuth Redirect URI Mismatch:**
- Ensure Azure App Registration has `http://localhost:8888/auth/callback`
- Check that no other redirect URIs are interfering

**Permission Denied Errors:**
- Verify all required scopes are granted in Azure App Registration
- Check that your Microsoft account has access to Teams and Planner

### Success Indicators

✅ **Server Running:** Console shows "Uvicorn running on http://0.0.0.0:8888"
✅ **OAuth URL Generated:** Contains redirect_uri=localhost%3A8888
✅ **Authentication Success:** Redirected to callback with success page
✅ **API Tests Pass:** Real Microsoft Graph API calls return data

## 📋 Next Steps

After successful authentication:
1. **Explore the Teams/Planner client methods** in your application
2. **Build your integration logic** using the authenticated user context
3. **Implement proper error handling** for production use
4. **Consider token refresh mechanisms** for long-running applications

The OAuth callback server provides a complete testing environment to validate your Microsoft Teams and Planner integration before deploying to production.