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
| `/add_wallet <address> <name>` | Add a wallet to monitor | `/add_wallet 0x742d35Cc... MyWallet` |
| `/remove_wallet <address>` | Remove a wallet from monitoring | `/remove_wallet 0x742d35Cc...` |
| `/list_wallets` | Show all your monitored wallets | `/list_wallets` |

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

**Token Transaction:**
```
🪙📥 Token Transaction - MyWallet

Type: Received USDC
Amount: 1000.0 USDC
Contract: 0xA0b86a33E6441e6079beB2e88B1eA0A3e9D99E9D
From: 0x8ba1f109551bD432803012645Hac136c35a96BC6
To: 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c
Time: 2024-01-15 14:32:45 UTC
Hash: 0xdef456...
Block: 18850125
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

### Database Schema

The bot uses SQLite with a simple schema:

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

### Transaction Detection

- **ETH Transactions**: Detected by monitoring transaction `from` and `to` fields in each block
- **ERC-20 Tokens**: Detected via `Transfer` event logs with signature `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`
- **ERC-721 NFTs**: Same `Transfer` event signature as ERC-20 but with token ID
- **ERC-1155 NFTs**: Detected via `TransferSingle` and `TransferBatch` events

### Monitoring Algorithm

1. Get current block number
2. Check all blocks since last processed block
3. For each block:
   - Scan all transactions for monitored wallet addresses
   - Query event logs for Transfer events involving monitored wallets
4. Process and format notifications
5. Send to relevant Telegram users
6. Update last processed block

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