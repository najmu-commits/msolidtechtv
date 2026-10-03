# MSOLIDTECHTV - Python Edition

This is the Python version of the SeeTV streaming application. All original functionality has been preserved.

## Setup Instructions

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and update the values:

```bash
copy .env.example .env
```

Then fill in the required settings for your deployment environment, such as:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `PIN`
- `SECRET_KEY`
- `PORT`
- MySQL variables if you enable database-backed access codes

### 3. Run the Application

```bash
python app.py
```

The application will start on `http://localhost:5000` by default.

### 4. Deploy

For deployment platforms such as Render, Railway, Fly.io, or Heroku, use:

```bash
gunicorn wsgi:app
```

### 5. Access the App

Open your browser and go to: `http://localhost:5000`

Enter PIN: ****

## Project Structure

```
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html      # Frontend interface
└── README.md           # This file
```

## Features

✅ PIN-based authentication (default: 1234)
✅ Channel browsing with 5 categories (All, Free, Sports, Movies, TV)
✅ Search functionality
✅ HLS and DASH video streaming
✅ Automatic token refresh
✅ Mobile-responsive design
✅ Shaka Player & HLS.js integration
✅ DRM support (ClearKeys)
✅ Error recovery and retry logic

## API Endpoints

- `POST /api/verify-pin` - Verify PIN
- `GET /api/channels` - Get all channels
- `POST /api/channels/filter` - Filter channels by category and search
- `GET /api/token` - Get current Azam token
- `GET /api/channel/<id>` - Get specific channel details
- `POST /api/direct-url` - Convert URL with token injection

## Configuration

Edit the config section in `app.py` to change:
- `SUPABASE_URL` - Supabase endpoint
- `SUPABASE_KEY` - Supabase API key
- `PIN` - Access PIN 

## Technology Stack

**Backend:** Flask + Python
**Frontend:** Vanilla HTML/CSS/JavaScript
**Video Players:** Shaka Player (DASH), HLS.js
**Database:** Supabase (REST API)

## Differences from Original

- ✅ All business logic moved to Python backend
- ✅ API-based communication between frontend and backend
- ✅ Better security with server-side verification
- ✅ Same user interface and experience
- ✅ All streaming features preserved
