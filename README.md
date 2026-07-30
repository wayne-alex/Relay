# Relay
A powerful, modern API client with built-in testing capabilities, environment management, and workflow automation. Built with Django, Alpine.js, and HTMX.

## 🚀 Features

### Core Features
- **Request Builder** - Full-featured HTTP client with support for all HTTP methods (GET, POST, PUT, PATCH, DELETE)
- **Environment Variables** - Manage variable sets per environment with mustache template syntax (`{{variable}}`)
- **Collection Management** - Organize and save requests in collections for easy reuse
- **Request History** - Automatically track all executed requests with response details

### Response Assertions & Testing
- **Automated Response Testing** - Define assertions that run automatically after each request
- **Multiple Assertion Types**:
  - Status Code validation
  - JSON Path extraction and comparison
  - Response Time thresholds
  - Header existence and value checking
  - Regex pattern matching on response body
- **Visual Feedback** - Pass/fail badges with detailed results
- **Toggle On/Off** - Enable or disable assertions globally

### Flows & Automation
- **Request Chaining** - Chain multiple saved requests together
- **Variable Extraction** - Extract values from responses (JSON paths, CSS selectors)
- **Dynamic Variables** - Pass extracted values to subsequent requests
- **Visual Flow Runner** - See each step execute with real-time results

### Developer Experience
- **cURL Import** - Paste cURL commands to auto-populate requests
- **Code Generation** - Generate code snippets in cURL, Python, and JavaScript
- **Response Preview** - View HTML responses with live preview
- **Table Extraction** - Extract and export HTML tables as CSV
- **Syntax Highlighting** - Beautiful code highlighting with Prism.js

## 🛠️ Tech Stack

- **Backend**: Django (Python)
- **Frontend**: Alpine.js, HTMX, Tailwind CSS
- **Code Highlighting**: Prism.js
- **Architecture**: SPA-like with server-side rendering

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/relay-api-engine.git
cd relay-api-engine

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file in the project root:

```env
DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///db.sqlite3
```

### Custom Settings
```python
# settings.py
RELAY_ENABLE_ASSERTIONS = True  # Enable/disable assertions globally
RELAY_MAX_HISTORY = 100         # Max history entries per user
RELAY_ENABLE_FLOWS = True       # Enable/disable flow automation
```

## 📝 Usage

### Creating and Running a Request
1. Enter your request URL and select the HTTP method
2. Add headers, authentication, and request body as needed
3. Click "Send" or use `⌘/Ctrl + Enter` shortcut
4. View the response with detailed information

### Setting Up Assertions
1. Click the "Assertions" button in the header
2. Add assertions with the "+ Add Assertion" button
3. Configure each assertion type, operator, and expected value
4. Toggle assertions on/off globally
5. Save your assertions - they'll run automatically on each request

### Building Flows
1. Click "Flows" in the sidebar and create a new flow
2. Add saved requests as steps
3. Configure extraction for each step (JSON paths or CSS selectors)
4. Run the flow to execute all steps sequentially
5. View the results and extracted variables

### Managing Environments
1. Click the environment button in the header
2. Create a new environment with a name and collection scope
3. Add key-value pairs for your variables
4. Use `{{variable}}` syntax in URLs, headers, or body
5. Switch environments to test different configurations

## 🏗️ Architecture

### Project Structure
```
relay/
├── core/                   # Main application
│   ├── models.py          # Database models (Collection, Environment, etc.)
│   ├── views.py           # API views and main workspace view
│   ├── urls.py            # URL routing
│   └── templates/         # HTML templates
│       ├── workspace.html # Main application interface
│       └── partials/      # Reusable template components
├── static/                # Static files
├── media/                 # User-uploaded files
└── manage.py              # Django management script
```

### Key Models
- **Collection**: Organizes saved requests
- **Environment**: Stores variable sets with optional collection scoping
- **SavedRequest**: Stores request configurations (method, URL, headers, body, auth)
- **RequestHistory**: Tracks all executed requests with response data
- **Flow**: Chains multiple saved requests with variable extraction
- **FlowStep**: Individual step within a flow with extraction configuration

## 🔒 Security

- All requests require authentication (Django's `@login_required` decorator)
- CSRF protection for all state-changing operations
- User isolation (each user only sees their own data)
- Sanitized input handling for HTML responses

## 🧪 Testing

```bash
# Run tests
python manage.py test

# Run with coverage
coverage run manage.py test
coverage report
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 for Python code
- Use Alpine.js for frontend interactivity
- Leverage HTMX for server communication
- Keep components modular and reusable
- Write tests for new features

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Django](https://www.djangoproject.com/)
- Frontend magic with [Alpine.js](https://alpinejs.dev/) and [HTMX](https://htmx.org/)
- Styled with [Tailwind CSS](https://tailwindcss.com/)
- Code highlighting by [Prism.js](https://prismjs.com/)

---

## API Endpoints

### Core Endpoints
- `POST /send-request/` - Execute a request
- `POST /save-request/` - Save a request to a collection
- `GET /history/list/` - Get request history
- `GET /collections/` - List collections

### Environment Endpoints
- `GET /api/environments/{id}/` - Get environment details
- `POST /api/environments/{id}/update/` - Update environment variables
- `POST /api/environments/save/` - Create new environment

### Assertion Endpoints
- `POST /api/save_assertions/` - Save assertion configurations
- `POST /api/run_assertions/` - Run assertions on response data

### Flow Endpoints
- `POST /api/flows/create/` - Create a new flow
- `GET /api/flows/{id}/` - Get flow details
- `POST /api/flows/{id}/run/` - Execute a flow

---

## Example Screenshots

### Main Interface
Clean, modern UI with request builder, response viewer, and assertion testing.

### Assertions Dashboard
Configure and run multiple assertions with visual pass/fail feedback.

### Flow Builder
Create complex workflows by chaining requests and extracting variables.

### Environment Management
Manage environment variables with collection scoping for different configurations.

---

**Built with ❤️ for developers who demand more from their API tools.**