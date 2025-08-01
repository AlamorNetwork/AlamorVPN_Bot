#!/bin/bash

# ==============================================================================
# AlamorVPN Bot Professional Installer & Manager v8.0 (Menu-Driven)
# ==============================================================================

# --- Color Codes ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- Variables ---
REPO_URL="https://github.com/AlamorNetwork/AlamorVPN_Bot.git"
INSTALL_DIR="/var/www/alamorvpn_bot"
BOT_SERVICE_NAME="alamorbot.service"
WEBHOOK_SERVICE_NAME="alamor_webhook.service"
SCRIPT_PATH_IN_INSTALL_DIR="/var/www/alamorvpn_bot/install.sh"
COMMAND_PATH="/usr/local/bin/alamorbot"

# --- Helper Functions ---
print_success() { echo -e "\n${GREEN}✅ $1${NC}\n"; }
print_error() { echo -e "\n${RED}❌ ERROR: $1${NC}\n"; }
print_info() { echo -e "\n${BLUE}ℹ️  $1${NC}\n"; }
print_warning() { echo -e "\n${YELLOW}⚠️  $1${NC}"; }
pause() { read -p "Press [Enter] key to continue..."; }

check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        print_error "This script must be run with root or sudo privileges."
        exit 1
    fi
}

# --- Main Logic Functions ---
setup_database() {
    print_info "--- Starting PostgreSQL Database Setup ---"
    read -p "$(echo -e ${YELLOW}"Please enter a name for the new database (e.g., alamor_db): "${NC})" db_name
    read -p "$(echo -e ${YELLOW}"Please enter a username for the database (e.g., alamor_user): "${NC})" db_user
    read -p "$(echo -e ${YELLOW}"Please enter a secure password for the database user: "${NC})" db_password

    # Create the PostgreSQL user and database
    sudo -u postgres psql -c "CREATE DATABASE $db_name;"
    sudo -u postgres psql -c "CREATE USER $db_user WITH PASSWORD '$db_password';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $db_name TO $db_user;"
    
    # Save credentials to the .env file
    echo -e "\n# --- PostgreSQL Database Settings ---" >> .env
    echo "DB_NAME=\"$db_name\"" >> .env
    echo "DB_USER=\"$db_user\"" >> .env
    echo "DB_PASSWORD=\"$db_password\"" >> .env
    echo "DB_HOST=\"localhost\"" >> .env
    echo "DB_PORT=\"5432\"" >> .env
    
    print_success "PostgreSQL database and user created successfully."
}

install_bot() {
    check_root
    print_info "Starting the complete installation of AlamorVPN Bot..."
    cd /root || { print_error "Cannot change to /root directory. Aborting."; exit 1; }

    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Project directory already exists. Reinstalling will delete all data."
        read -p "Are you sure you want to continue? (y/n): " confirm_reinstall
        if [[ "$confirm_reinstall" == "y" ]]; then
            remove_bot_internal
        else
            print_info "Installation canceled."; exit 0
        fi
    fi

    print_info "Step 1: Updating system and installing prerequisites..."
    apt-get update && apt-get install -y python3 python3-pip python3.10-venv git zip nginx certbot python3-certbot-nginx postgresql postgresql-contrib
    if [ $? -ne 0 ]; then print_error "Failed to install system dependencies. Aborting."; exit 1; fi

    sudo systemctl start postgresql
    sudo systemctl enable postgresql

    print_info "Step 2: Cloning the project repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR" || exit 1
    
    print_info "Step 3: Setting up Python environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    print_info "Step 4: Configuring main bot variables..."
    setup_env_file
    
    print_info "Step 5: Configuring PostgreSQL Database..."
    setup_database

    print_info "Step 6: Configuring domain and payment gateway..."
    setup_ssl_and_nginx
    
    print_info "Step 7: Setting up persistent services..."
    setup_services
    
    print_info "Step 8: Creating the 'alamorbot' management command..."
    # Make the script executable
    sudo chmod +x "$SCRIPT_PATH_IN_INSTALL_DIR"
    # Create a symbolic link in /usr/local/bin
    if [ -f "$COMMAND_PATH" ]; then
        sudo rm "$COMMAND_PATH"
    fi
    sudo ln -s "$SCRIPT_PATH_IN_INSTALL_DIR" "$COMMAND_PATH"
    
    print_success "Installation complete! You can now manage the bot by typing 'alamorbot' in the terminal."
}
setup_env_file() {
    local PYTHON_EXEC="$INSTALL_DIR/.venv/bin/python3"
    print_info "--- Starting .env file configuration ---"
    read -p "$(echo -e ${YELLOW}"Please enter your Telegram Bot Token: "${NC})" bot_token
    read -p "$(echo -e ${YELLOW}"Please enter your numeric Admin ID: "${NC})" admin_id
    read -p "$(echo -e ${YELLOW}"Please enter your bot's username (without @): "${NC})" bot_username
    
    print_info "Generating encryption key..."
    encryption_key=$($PYTHON_EXEC code-generate.py)

    print_warning "CRITICAL: Please save this encryption key in a safe place!"
    echo -e "${GREEN}Your Encryption Key is: $encryption_key${NC}"
    read -p "Press [Enter] to continue after you have saved the key."

    cat > .env <<- EOL
BOT_TOKEN_ALAMOR="$bot_token"
ADMIN_IDS_ALAMOR="[$admin_id]"
BOT_USERNAME_ALAMOR="$bot_username"
DATABASE_NAME_ALAMOR="database/alamor_vpn.db"
ENCRYPTION_KEY_ALAMOR="$encryption_key"
EOL
    print_success ".env file created successfully."
}

# در فایل install.sh
create_system_command() {
    print_info "Setting up the 'alamorbot' system command..."
    if [ ! -f "$SCRIPT_PATH_IN_INSTALL_DIR" ]; then
        print_error "install.sh not found in $INSTALL_DIR. Please run the full installation first."
        return 1
    fi
    # Make the script executable
    sudo chmod +x "$SCRIPT_PATH_IN_INSTALL_DIR"
    # Create a symbolic link in /usr/local/bin
    if [ -L "$COMMAND_PATH" ]; then
        sudo rm "$COMMAND_PATH"
    fi
    sudo ln -s "$SCRIPT_PATH_IN_INSTALL_DIR" "$COMMAND_PATH"
    print_success "Command 'alamorbot' is now available system-wide."
}
setup_ssl_and_nginx() {
    print_info "\n--- Configuring SSL for Payment Domain ---"
    read -p "Do you want to configure an online payment domain? (y/n): " setup_ssl
    if [[ "$setup_ssl" != "y" ]]; then print_success "Skipping SSL configuration."; return; fi

    read -p "$(echo -e ${YELLOW}"Please enter your payment domain (e.g., pay.yourdomain.com): "${NC})" payment_domain
    read -p "$(echo -e ${YELLOW}"Please enter a valid email for Let's Encrypt notifications: "${NC})" admin_email
    
    NGINX_CONFIG_PATH="/etc/nginx/sites-available/alamor_webhook"

    # --- New, Robust Logic ---
    # 1. Create a minimal Nginx config to pass the initial check.
    print_info "Step 5.1: Creating temporary Nginx configuration..."
    sudo cat > "$NGINX_CONFIG_PATH" <<- EOL
server {
    listen 80;
    server_name $payment_domain;
    root /var/www/html;
    index index.html index.htm;
}
EOL

    sudo ln -s -f "$NGINX_CONFIG_PATH" /etc/nginx/sites-enabled/
    if [ -f "/etc/nginx/sites-enabled/default" ]; then sudo rm "/etc/nginx/sites-enabled/default"; fi
    
    sudo systemctl restart nginx
    if [ $? -ne 0 ]; then print_error "Nginx failed to start with temporary config. Aborting."; exit 1; fi
    print_success "Nginx started successfully with temporary config."

    # 2. Run Certbot using the --nginx plugin.
    print_info "Step 5.2: Requesting SSL certificate with Certbot..."
    sudo certbot --nginx -d "$payment_domain" --email "$admin_email" --agree-tos --no-eff-email --redirect --non-interactive
    if [ $? -ne 0 ]; then print_error "Failed to issue SSL certificate. Please ensure the domain is correctly pointed to the server's IP."; exit 1; fi
    print_success "SSL certificate issued and installed by Certbot."
    
    # 3. Overwrite the Nginx config with the final reverse proxy settings.
    print_info "Step 5.3: Configuring Nginx as a Reverse Proxy..."
    sudo cat > "$NGINX_CONFIG_PATH" <<- EOL
server {
    listen 80;
    server_name $payment_domain;
    return 301 https://\$host\$request_uri;
}
server {
    listen 443 ssl http2;
    server_name $payment_domain;
    ssl_certificate /etc/letsencrypt/live/$payment_domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$payment_domain/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOL
    sudo systemctl restart nginx
    print_success "Nginx successfully configured as a reverse proxy."
    
    echo -e "\n# Webhook Settings" >> .env
    echo "WEBHOOK_DOMAIN=\"$payment_domain\"" >> .env
    print_success "Payment domain saved to .env file."
}
setup_services() {
    print_info "Creating systemd services..."
    # Bot Service
    sudo cat > /etc/systemd/system/$BOT_SERVICE_NAME <<- EOL
[Unit]
Description=Alamor VPN Telegram Bot
After=network.target
[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python3 $INSTALL_DIR/main.py
Restart=always
RestartSec=10s
[Install]
WantedBy=multi-user.target
EOL

    # Webhook Service
    if grep -q "WEBHOOK_DOMAIN" .env; then
        sudo cat > /etc/systemd/system/$WEBHOOK_SERVICE_NAME <<- EOL
[Unit]
Description=AlamorBot Webhook Server for Payments
After=network.target
[Service]
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python3 $INSTALL_DIR/webhook_server.py
Restart=always
RestartSec=10s
[Install]
WantedBy=multi-user.target
EOL
        sudo systemctl enable $WEBHOOK_SERVICE_NAME
        sudo systemctl start $WEBHOOK_SERVICE_NAME
    fi
    sudo systemctl daemon-reload
    sudo systemctl enable $BOT_SERVICE_NAME
    sudo systemctl start $BOT_SERVICE_NAME
    print_success "Bot and Webhook services have been enabled and started."
}

update_bot() {
    print_info "Updating the bot from the 'main' branch on GitHub..."
    sudo systemctl stop $BOT_SERVICE_NAME $WEBHOOK_SERVICE_NAME 2>/dev/null
    git pull origin main
    if [ $? -ne 0 ]; then print_error "Failed to pull updates. Aborting."; pause; return; fi
    
    print_info "Installing/Updating Python dependencies..."
    $INSTALL_DIR/.venv/bin/pip install -r requirements.txt
    
    print_info "Restarting services..."
    sudo systemctl start $BOT_SERVICE_NAME $WEBHOOK_SERVICE_NAME 2>/dev/null
    print_success "Bot updated and restarted successfully."
}

remove_bot_internal() {
    print_info "Stopping and disabling services..."
    sudo systemctl stop $BOT_SERVICE_NAME $WEBHOOK_SERVICE_NAME 2>/dev/null
    sudo systemctl disable $BOT_SERVICE_NAME $WEBHOOK_SERVICE_NAME 2>/dev/null
    
    print_info "Removing service files..."
    sudo rm -f "/etc/systemd/system/$BOT_SERVICE_NAME"
    sudo rm -f "/etc/systemd/system/$WEBHOOK_SERVICE_NAME"
    sudo systemctl daemon-reload
    
    print_info "Removing Nginx config file..."
    sudo rm -f "/etc/nginx/sites-enabled/alamor_webhook"
    sudo rm -f "/etc/nginx/sites-available/alamor_webhook"
    sudo systemctl restart nginx 2>/dev/null
    
    print_info "Removing certificate files (acme.sh)..."
    DOMAIN_TO_REMOVE=$(grep 'WEBHOOK_DOMAIN' "$INSTALL_DIR/.env" | cut -d '=' -f2 | tr -d '"')
    if [ -n "$DOMAIN_TO_REMOVE" ] && [ -d "$HOME/.acme.sh" ]; then
        ~/.acme.sh/acme.sh --revoke -d "$DOMAIN_TO_REMOVE"
        ~/.acme.sh/acme.sh --remove -d "$DOMAIN_TO_REMOVE"
    fi
}

remove_bot() {
    check_root
    print_warning "This operation will completely remove the bot, its services, and configurations."
    read -p "Are you sure? (y/n): " confirm
    if [[ "$confirm" != "y" ]]; then print_info "Operation canceled."; exit 0; fi
    
    remove_bot_internal
    
    print_info "Removing project directory..."
    rm -rf "$INSTALL_DIR"
    
    print_success "Removal complete."
}

create_backup() {
    print_info "Creating backup file..."
    BACKUP_NAME="alamor_backup_$(date +%Y-%m-%d_%H-%M).zip"
    DB_PATH=$(grep "DATABASE_NAME_ALAMOR" .env | cut -d '=' -f2 | tr -d '"')
    if [ -f ".env" ] && [ -f "$DB_PATH" ]; then
        zip "$BACKUP_NAME" .env "$DB_PATH"
        print_success "Backup file created as $BACKUP_NAME in the current directory."
    else
        print_error "Could not find .env or database file to backup."
    fi
}

# ==============================================================================
# SECTION: Menu System
# ==============================================================================

show_main_menu() {
    clear
    echo -e "${BLUE}=====================================${NC}"
    echo -e "${GREEN}      AlamorVPN Bot Manager        ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo " 1. Show Service Status"
    echo " 2. View Live Logs"
    echo " 3. Restart Service"
    echo " 4. Stop Service"
    echo "-------------------------------------"
    echo " 5. Update Bot"
    echo " 6. Create Backup"
    echo -e "${RED} 7. Remove Bot (H DANGER H)${NC}"
    echo "-------------------------------------"
    echo " 0. Exit"
    echo -e "${BLUE}=====================================${NC}"
}

handle_menu_choice() {
    read -p "Please enter your choice [0-7]: " choice
    case $choice in
        1)
            sudo systemctl --no-pager status $BOT_SERVICE_NAME
            pause
            ;;
        2)
            sudo journalctl -u $BOT_SERVICE_NAME -f --no-pager
            ;;
        3)
            sudo systemctl restart $BOT_SERVICE_NAME 2>/dev/null
            print_success "Service restarted."
            pause
            ;;
        4)
            sudo systemctl stop $BOT_SERVICE_NAME 2>/dev/null
            print_success "Service stopped."
            pause
            ;;
        5)
            update_bot
            pause
            ;;
        6)
            create_backup
            pause
            ;;
        7)
            read -p "$(print_warning 'This is a destructive action. Are you sure? (y/n): ')" confirm
            if [[ "$confirm" == "y" ]]; then
                remove_bot
                echo "Exiting now."
                exit 0
            else
                print_info "Removal canceled."
                pause
            fi
            ;;
        0)
            echo "Exiting."
            exit 0
            ;;
        *)
            print_error "Invalid option."
            pause
            ;;
    esac
}

# ==============================================================================
# SECTION: Main Script Logic
# ==============================================================================

if [[ "$1" == "install" ]]; then
    install_bot
    exit 0
fi

if [[ "$1" == "setup_command" ]]; then
    check_root
    create_system_command
    exit 0
fi

check_root
if [ ! -d "$INSTALL_DIR" ]; then
    print_error "Bot is not installed. Run with 'install' argument."
    exit 1
fi
cd "$INSTALL_DIR"

while true; do
    show_main_menu
    handle_menu_choice
done