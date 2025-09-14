# Xi Bot - Ethereum Wallet Activity Monitor

A powerful Telegram bot that monitors Ethereum wallet activity and sends real-time notifications for ETH, ERC-20 token, and NFT transactions.

![Python](https://img.shields.io/badge/python-v3.11+-blue.svg)
![Telegram Bot](https://img.shields.io/badge/telegram-bot-blue.svg)
![Ethereum](https://img.shields.io/badge/ethereum-mainnet-green.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Features

- 🔗 **Real-time Monitoring** - Checks for new transactions every 10 seconds
- 💰 **ETH Transactions** - Monitor incoming and outgoing ETH transfers
- 🪙 **ERC-20 Tokens** - Track token transfers with amount detection
- 🎨 **NFTs** - Monitor ERC-721 and ERC-1155 NFT transfers
- 📱 **Instant Notifications** - Telegram alerts with transaction details
- 👤 **Multi-user Support** - Each user manages their own wallet list
- 🗃️ **Lightweight Storage** - Only stores wallet mappings, no transaction history
- 🏷️ **Custom Names** - Assign friendly names to your wallets

## 📋 Requirements

- Python 3.11 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Ethereum node access (Alchemy, Infura, QuickNode, etc.)
- Internet connection

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/Xi-Bot.git
cd Xi-Bot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the Bot

Copy the environment template:
```bash
cp .env.example .env
```

Edit `.env` with your configuration:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
WEB3_PROVIDER_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY
```

### 4. Start the Bot

```bash
python start_bot.py
```

That's it! Your bot is now running and ready to monitor wallets.

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | ✅ Yes | Bot token from BotFather | `1234567890:ABCdef...` |
| `WEB3_PROVIDER_URL` | ✅ Yes | Ethereum node URL | `https://eth-mainnet.g.alchemy.com/v2/KEY` |
| `DATABASE_PATH` | ❌ No | SQLite database file path | `xi_bot.db` (default) |
| `MONITOR_INTERVAL` | ❌ No | Check interval in seconds | `10` (default) |
| `DEBUG` | ❌ No | Enable debug logging | `false` (default) |

### Getting API Keys

#### Alchemy (Recommended)
1. Sign up at [alchemy.com](https://alchemy.com)
2. Create a new app for Ethereum Mainnet
3. Copy the HTTPS URL to `WEB3_PROVIDER_URL`

#### Infura
1. Sign up at [infura.io](https://infura.io)
2. Create a new project
3. Use: `https://mainnet.infura.io/v3/YOUR_PROJECT_ID`

#### QuickNode
1. Sign up at [quicknode.com](https://quicknode.com)
2. Create an Ethereum endpoint
3. Use the provided HTTPS URL

### Creating a Telegram Bot
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow instructions
3. Save the bot token to your `.env` file
4. Optionally customize your bot with `/setdescription`, `/setabouttext`, etc.

## 🎯 Usage

### Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Show welcome message and instructions | `/start` |
| `/menu` | Display interactive menu with buttons | `/menu` |
| `/add_wallet <address> <name>` | Add a wallet to monitor | `/add_wallet 0x742d35Cc... MyWallet` |
| `/remove_wallet <address>` | Remove a wallet from monitoring | `/remove_wallet 0x742d35Cc...` |
| `/list_wallets` | Show all your monitored wallets | `/list_wallets` |
| `/get_balance <address>` | Get comprehensive wallet balance | `/get_balance 0x742d35Cc...` |
| `/get_balance <address> <token>` | Get specific token balance | `/get_balance 0x742d35Cc... 0xdAC17F958...` |
| `/check_transactions` | Manually check for new transactions | `/check_transactions` |
| `/test` | Test Web3 connection status | `/test` |

### Example Workflow

1. **Start the bot**: Send `/start` to get instructions
2. **Add a wallet**: `/add_wallet 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c MyMainWallet`
3. **Monitor**: The bot will send notifications for all transactions
4. **Manage**: Use `/list_wallets` to see all wallets, `/remove_wallet` to stop monitoring

### Notification Format

**ETH Transaction:**
```
📤 ETH Transaction - MyWallet

Type: Sent ETH
Amount: 0.150000 ETH
From: 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c
To: 0x8ba1f109551bD432803012645Hac136c35a96BC6
Time: 2024-01-15 14:30:22 UTC
Hash: 0xabc123...
Block: 18850123
```

**Balance Check Results:**
```
💰 Balance Summary

ETH: 2.450000 ETH
Tokens: 5 types
Token Value: 0.850000 ETH
🎯 Total Portfolio: 3.300000 ETH

Top Tokens:
• USDT: ~0.500000 ETH
• LINK: ~0.200000 ETH
• UNI: ~0.150000 ETH
```



## 📁 Project Structure

```
Xi-Bot/
├── xi_bot.py              # Main bot implementation
├── start_bot.py           # Startup script with validation
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
├── README.md             # This file
├── LICENSE               # MIT License
└── data/                 # Database and logs (created at runtime)
    ├── xi_bot.db         # SQLite database
    └── xi_bot.log        # Application logs
```

## 🔧 Technical Details

### Core Components

The Xi Bot is built with three main classes that handle different aspects of the system:

#### DatabaseManager Class
Handles all SQLite database operations for persistent storage:
- **`init_database()`** - Creates the wallets table with proper schema and constraints
- **`add_wallet()`** - Adds a new wallet address for a user with custom naming
- **`remove_wallet()`** - Removes a wallet from monitoring for a specific user
- **`get_user_wallets()`** - Retrieves all wallets belonging to a specific user
- **`get_all_wallets()`** - Gets all wallets mapped to user IDs for system-wide monitoring
- **`get_wallet_name()`** - Fetches the custom name assigned to a wallet

#### TransactionMonitor Class
Manages all Ethereum blockchain interactions and monitoring:
- **`__init__()`** - Initializes Web3 connection and Alchemy SDK integration
- **`is_valid_address()`** - Validates Ethereum address format
- **`format_address()`** - Converts addresses to checksum format for consistency
- **`get_address_balance()`** - Retrieves comprehensive balance data including ETH and ERC-20 tokens
- **`_get_token_balance()`** - Gets balance for a specific ERC-20 token contract
- **`_scan_popular_tokens()`** - Scans wallet for balances of popular tokens (USDT, USDC, etc.)
- **`_scan_tokens_via_alchemy()`** - Uses Alchemy SDK for enhanced token discovery
- **`_get_token_eth_value()`** - Calculates token values in ETH using market data
- **`get_new_transactions()`** - Monitors blockchain for new transactions on watched wallets
- **`_process_eth_transaction()`** - Processes and formats ETH transaction data

#### XiBot Class
Main Telegram bot interface and orchestration:
- **`setup_handlers()`** - Configures all Telegram command and callback handlers
- **`start_command()`** - Handles /start command with welcome message and menu
- **`menu_command()`** - Displays interactive menu with action buttons
- **`button_callback()`** - Processes all inline keyboard button interactions
- **`add_wallet_command()`** - Processes /add_wallet command with validation
- **`remove_wallet_command()`** - Handles wallet removal requests
- **`list_wallets_command()`** - Shows user's monitored wallets
- **`get_balance_command()`** - Retrieves and displays comprehensive wallet balances
- **`check_transactions_command()`** - Manually checks for new transactions
- **`send_transaction_notification()`** - Sends formatted transaction alerts to users
- **`monitor_transactions()`** - Main monitoring loop that runs continuously
- **`start()`** - Initializes and starts the bot with monitoring

### Database Schema

The bot uses SQLite with a simple but effective schema:

```sql
CREATE TABLE wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet_address TEXT NOT NULL,
    name_address TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, wallet_address)
);
```

### Balance Checking Features

The bot provides comprehensive balance checking with:
- **ETH Balance**: Native Ethereum balance in ETH units
- **Token Discovery**: Automatic detection of ERC-20 tokens using popular token lists
- **Enhanced Scanning**: Alchemy SDK integration for discovering all tokens in a wallet
- **Value Calculation**: Token values calculated in ETH equivalent using CoinGecko API
- **Portfolio Summary**: Total portfolio value combining ETH and token holdings
- **Sorted Display**: Tokens sorted by value (highest first) for better user experience

### Transaction Detection

- **ETH Transactions**: Detected by monitoring transaction `from` and `to` fields in each block
- **ERC-20 Tokens**: Detected via `Transfer` event logs with signature `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`
- **Real-time Monitoring**: Continuous blockchain scanning every 10 seconds
- **Multi-user Support**: Each user's wallets are tracked independently

### Monitoring Algorithm

1. Get current block number from Ethereum network
2. Check all blocks since last processed block
3. For each block:
   - Scan all transactions for monitored wallet addresses
   - Process ETH transfers (incoming/outgoing)
   - Extract transaction metadata (amount, gas, timestamp)
4. Format and send notifications to relevant users
5. Update last processed block number
6. Repeat cycle every 10 seconds

## 🛠️ Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/Xi-Bot.git
cd Xi-Bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your configuration

# Run in development mode
DEBUG=true python start_bot.py
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Code Structure

- `xi_bot.py` - Main bot implementation with classes:
  - `DatabaseManager` - SQLite database operations
  - `TransactionMonitor` - Ethereum blockchain monitoring
  - `XiBot` - Telegram bot interface and main orchestration

- `start_bot.py` - Production startup script with:
  - Configuration validation
  - Dependency checking
  - Error handling and logging setup

## 🔍 Troubleshooting

### Common Issues

**Bot not responding:**
- Check if the bot token is correct
- Verify the bot is running (`python start_bot.py`)
- Check logs in `xi_bot.log`

**No transaction notifications:**
- Verify Ethereum node URL is working
- Check if wallets are added correctly with `/list_wallets`
- Monitor logs for connection errors

**Invalid address errors:**
- Ensure Ethereum addresses are in correct format (0x...)
- Use checksummed addresses when possible

**Rate limiting:**
- Increase `MONITOR_INTERVAL` if getting rate limited
- Consider using paid Ethereum node service with higher limits

**Database errors:**
- Check file permissions for database directory
- Verify SQLite is properly installed

### Logs and Monitoring

The bot logs to both console and `xi_bot.log` file:
- `INFO` level: Normal operations, transactions processed
- `WARNING` level: Recoverable errors, configuration issues
- `ERROR` level: Critical errors that need attention

Enable debug logging:
```bash
DEBUG=true python start_bot.py
```

### Performance Optimization

For high-volume monitoring:
- Use WebSocket connection instead of HTTP polling
- Implement connection pooling
- Add Redis for caching frequently accessed data
- Consider using PostgreSQL for better concurrent access

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Commit your changes: `git commit -am 'Add feature'`
5. Push to the branch: `git push origin feature-name`
6. Submit a pull request

### Development Guidelines

- Follow PEP 8 style guide
- Add docstrings to all functions and classes
- Include unit tests for new features
- Update documentation for API changes
- Use type hints where appropriate

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [python-telegram-bot](https://python-telegram-bot.org/) - Telegram Bot API wrapper
- [web3.py](https://web3py.readthedocs.io/) - Ethereum blockchain interaction
- [Alchemy](https://alchemy.com/) - Recommended Ethereum node provider

## 📞 Support

- 📧 Email: support@xibot.com
- 💬 Telegram: [@XiBotSupport](https://t.me/XiBotSupport)
- 🐛 Issues: [GitHub Issues](https://github.com/yourusername/Xi-Bot/issues)

---

**⚠️ Disclaimer:** This bot monitors public blockchain data. Never share your private keys or sensitive information. The bot only tracks wallet addresses, not private keys or wallet access.