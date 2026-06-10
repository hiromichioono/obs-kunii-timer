#!/bin/bash
# obs-kunii-timer Startup Script for Mac

# Move to the directory where the script is located
cd "$(dirname "$0")"

# Text Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== obs-kunii-timer Setup Check ===${NC}"

# 1. Check Python installation
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed.${NC}"
    echo "Please install Python 3.10 or higher from https://www.python.org/"
    exit 1
fi

# 2. Setup Virtual Environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment (venv) not found. Creating...${NC}"
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to create virtual environment.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Virtual environment created successfully.${NC}"
fi

# 3. Activate venv
source venv/bin/activate

# 4. Install/Update dependencies
echo -e "${YELLOW}Checking/Installing dependencies...${NC}"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to install dependencies.${NC}"
    exit 1
fi

# 5. Check .env (optional reminder)
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Note: .env file not found.${NC}"
    echo "YouTube API functions will be limited (Automatic stream detection disabled)."
    echo "To enable it, create a .env file with YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID."
    echo "Refer to README.md for more details."
    echo ""
fi

echo -e "${GREEN}=== Starting System ===${NC}"
python chat_server.py
