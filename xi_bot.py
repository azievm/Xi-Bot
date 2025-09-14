#!/usr/bin/env python3
"""
Xi Bot - Telegram bot for tracking Ethereum wallet activity

This bot allows users to:
- Monitor Ethereum wallet addresses for incoming/outgoing transactions
- Check comprehensive wallet balances including ETH and ERC-20 tokens
- Receive real-time notifications via Telegram when transactions occur
- Track token values in ETH equivalent using market data
- Manage multiple wallets with custom names for easy identification

The bot uses Web3 to interact with the Ethereum blockchain and supports
both basic RPC providers and enhanced services like Alchemy for better
token discovery and metadata retrieval.
"""

import asyncio
import sqlite3
import logging
import os
import sys
import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
import aiohttp
from web3 import Web3
from web3.exceptions import ContractLogicError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Alchemy SDK imports
try:
    from alchemy_sdk import Alchemy, Network, AlchemySettings
except ImportError:
    print("Warning: Alchemy SDK not installed. Run: pip install alchemy-sdk")
    Alchemy = None
    Network = None
    AlchemySettings = None

# Configure logging system for debugging and monitoring
# This sets up structured logging with timestamps and log levels
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ERC-20 Transfer event signature - used to identify token transfer events on the blockchain
# This is the keccak256 hash of "Transfer(address,address,uint256)" event signature
ERC20_TRANSFER_SIGNATURE = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# ERC-20 Application Binary Interface (ABI) definitions
# These define the standard functions we need to interact with ERC-20 tokens:
# - balanceOf: get token balance for an address
# - symbol: get token symbol (e.g., "USDT", "LINK")
# - decimals: get number of decimal places for the token
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]


class DatabaseManager:
    """
    Handles SQLite database operations for wallet storage
    
    This class manages the persistent storage of user wallet addresses
    and their associated names. It provides methods to:
    - Add new wallets for users
    - Remove wallets from monitoring
    - Retrieve user's wallet lists
    - Get all wallets for system-wide monitoring
    """

    def __init__(self, db_path: str = "xi_bot.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """
        Initialize the database with wallets table
        
        Creates the SQLite database and wallets table if they don't exist.
        The table stores user_id, wallet_address, custom name, and creation timestamp.
        Uses UNIQUE constraint to prevent duplicate wallet entries per user.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                name_address TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, wallet_address)
            )
        """)

        conn.commit()
        conn.close()

    def add_wallet(self, user_id: int, wallet_address: str, name_address: str) -> bool:
        """
        Add a wallet for a user
        
        Args:
            user_id: Telegram user ID
            wallet_address: Ethereum wallet address (will be normalized to lowercase)
            name_address: Custom name for the wallet (e.g., "My Main Wallet")
            
        Returns:
            bool: True if wallet was added successfully, False if it already exists
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO wallets (user_id, wallet_address, name_address) VALUES (?, ?, ?)",
                (user_id, wallet_address.lower(), name_address)
            )

            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_wallet(self, user_id: int, wallet_address: str) -> bool:
        """
        Remove a wallet for a user
        
        Args:
            user_id: Telegram user ID
            wallet_address: Ethereum wallet address to remove
            
        Returns:
            bool: True if wallet was removed, False if wallet wasn't found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM wallets WHERE user_id = ? AND wallet_address = ?",
            (user_id, wallet_address.lower())
        )

        affected_rows = cursor.rowcount
        conn.commit()
        conn.close()

        return affected_rows > 0

    def get_user_wallets(self, user_id: int) -> List[Dict]:
        """
        Get all wallets for a specific user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            List[Dict]: List of wallet dictionaries with 'address' and 'name' keys
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT wallet_address, name_address FROM wallets WHERE user_id = ?",
            (user_id,)
        )

        wallets = []
        for row in cursor.fetchall():
            wallets.append({
                'address': row[0],
                'name': row[1]
            })

        conn.close()
        return wallets

    def get_all_wallets(self) -> Dict[str, List[int]]:
        """
        Get all wallets mapped to user IDs for monitoring
        
        This method is used by the monitoring system to get all wallet addresses
        that need to be watched, along with the user IDs that should be notified
        when transactions occur on those wallets.
        
        Returns:
            Dict[str, List[int]]: Dictionary mapping wallet addresses to lists of user IDs
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT wallet_address, user_id FROM wallets")

        wallet_users = {}
        for row in cursor.fetchall():
            wallet_address = row[0]
            user_id = row[1]

            if wallet_address not in wallet_users:
                wallet_users[wallet_address] = []
            wallet_users[wallet_address].append(user_id)

        conn.close()
        return wallet_users

    def get_wallet_name(self, user_id: int, wallet_address: str) -> Optional[str]:
        """
        Get wallet name for a specific user and wallet
        
        Args:
            user_id: Telegram user ID
            wallet_address: Ethereum wallet address
            
        Returns:
            Optional[str]: Custom wallet name if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name_address FROM wallets WHERE user_id = ? AND wallet_address = ?",
            (user_id, wallet_address.lower())
        )

        result = cursor.fetchone()
        conn.close()

        return result[0] if result else None


class TransactionMonitor:
    """
    Monitors Ethereum blockchain for new transactions and balance queries
    
    This class handles all blockchain interactions including:
    - Connecting to Ethereum nodes via Web3 providers
    - Monitoring blocks for new transactions
    - Retrieving wallet balances (ETH and ERC-20 tokens)
    - Token discovery using popular token lists and Alchemy SDK
    - Price data integration for token valuation in ETH
    """

    def __init__(self, web3_provider_url: str):
        """
        Initialize the transaction monitor
        
        Sets up Web3 connection, initializes Alchemy SDK if available,
        and establishes the starting block for transaction monitoring.
        
        Args:
            web3_provider_url: Ethereum node URL (e.g., Alchemy, Infura, QuickNode)
        """
        self.web3 = Web3(Web3.HTTPProvider(web3_provider_url))
        # Start monitoring from recent blocks instead of genesis to avoid processing old data
        # This improves startup time and focuses on current activity
        current_block = self.web3.eth.block_number
        self.last_checked_block = max(0, current_block - 100)  # Start from last 100 blocks
        
        # Initialize Alchemy SDK if available for enhanced token discovery
        # Alchemy provides better token metadata and balance discovery than basic Web3
        self.alchemy = None
        if Alchemy and "alchemy.com" in web3_provider_url:
            try:
                # Extract API key from Alchemy URL format
                # Alchemy URLs typically end with the API key after /v2/
                api_key = web3_provider_url.split("/v2/")[-1] if "/v2/" in web3_provider_url else None
                if api_key:
                    settings = AlchemySettings(
                        api_key=api_key,
                        network=Network.ETH_MAINNET
                    )
                    self.alchemy = Alchemy(settings)
                    logger.info("Alchemy SDK initialized successfully")
                
            except Exception as e:
                logger.warning(f"Failed to initialize Alchemy SDK: {e}")
        
        # Test the Web3 connection to ensure we can communicate with the Ethereum network
        if not self.web3.is_connected():
            raise Exception(f"Failed to connect to Ethereum node at {web3_provider_url}")
        
        logger.info(f"Connected to Ethereum network. Latest block: {self.web3.eth.block_number}")

    def is_valid_address(self, address: str) -> bool:
        """
        Check if an Ethereum address is valid
        
        Validates that the provided string is a properly formatted Ethereum address.
        
        Args:
            address: String to validate as Ethereum address
            
        Returns:
            bool: True if valid Ethereum address, False otherwise
        """
        try:
            return Web3.is_address(address)
        except:
            return False

    def format_address(self, address: str) -> str:
        """
        Format address to checksum format
        
        Converts an Ethereum address to the standard checksum format
        which uses mixed case to provide error detection.
        
        Args:
            address: Ethereum address string
            
        Returns:
            str: Checksummed address or cleaned lowercase address if checksum fails
        """
        try:
            # Remove any whitespace and convert to lowercase for processing
            clean_address = address.strip().lower()
            return Web3.to_checksum_address(clean_address)
        except:
            # If checksum conversion fails, return cleaned lowercase address
            return address.strip().lower()

    async def get_address_balance(self, address: str, token_contract_address: Optional[str] = None, scan_all_tokens: bool = False) -> Dict:
        """
        Get comprehensive balance information for an Ethereum address
        
        This method retrieves ETH balance and optionally scans for ERC-20 tokens.
        It can either check a specific token or scan for all popular tokens.
        Token values are calculated in ETH equivalent using market data.
        
        Args:
            address: Ethereum wallet address to check
            token_contract_address: Specific ERC-20 token contract to check (optional)
            scan_all_tokens: Whether to scan for all popular tokens (default: False)
            
        Returns:
            Dict: Balance data including ETH balance, token list, and portfolio summary
        """
        try:
            # Check Web3 connection status before proceeding
            if not self.web3.is_connected():
                logger.error("Web3 connection lost")
                return {'error': 'Web3 connection lost'}
            
            address = self.format_address(address)
            logger.info(f"Getting balance for address: {address}")
            
            balance_data = {
                'address': address, 
                'eth_balance': 0, 
                'tokens': [], 
                'token_count': 0,
                'total_usd': 0.0,
                'error': None
            }

            # Get ETH balance from the blockchain
            try:
                eth_balance_wei = self.web3.eth.get_balance(address)
                logger.info(f"Raw ETH balance in wei: {eth_balance_wei}")
                
                # Convert from wei (smallest ETH unit) to ETH
                eth_balance = self.web3.from_wei(eth_balance_wei, 'ether')
                logger.info(f"Converted ETH balance: {eth_balance}")
                
                balance_data['eth_balance'] = float(eth_balance)
                logger.info(f"Final ETH balance: {balance_data['eth_balance']} ETH")
                
            except Exception as e:
                error_msg = f"Error getting ETH balance: {e}"
                logger.error(error_msg)
                balance_data['error'] = error_msg
                return balance_data

            # Get token balances based on the request type
            if token_contract_address:
                # Get balance for a specific token contract
                try:
                    token_balance = await self._get_token_balance(address, token_contract_address)
                    if token_balance:
                        balance_data['tokens'].append(token_balance)
                except Exception as e:
                    logger.error(f"Error getting token balance: {e}")
            elif scan_all_tokens:
                # Use Alchemy's enhanced token discovery for comprehensive scanning
                try:
                    await self._scan_tokens_via_alchemy(address, balance_data)
                    logger.info(f"Alchemy scan completed, found {len(balance_data['tokens'])} tokens")
                except Exception as e:
                    logger.warning(f"Alchemy scan failed: {e}")
                    # Fallback to scanning popular tokens if Alchemy fails
                    await self._scan_popular_tokens(address, balance_data)
            
            # Calculate portfolio statistics and token metrics
            balance_data['token_count'] = len(balance_data['tokens'])
            
            # Calculate total portfolio value in ETH equivalent
            total_token_eth_value = sum(token.get('eth_value', 0) for token in balance_data['tokens'])
            balance_data['total_token_eth_value'] = total_token_eth_value
            balance_data['total_portfolio_eth'] = balance_data['eth_balance'] + total_token_eth_value
            
            # Sort tokens by ETH value (highest first) for better display
            balance_data['tokens'].sort(key=lambda x: x.get('eth_value', 0), reverse=True)
            
            logger.info(f"Portfolio summary: {balance_data['eth_balance']:.6f} ETH + {total_token_eth_value:.6f} ETH in tokens = {balance_data['total_portfolio_eth']:.6f} ETH total")

            return balance_data
            
        except Exception as e:
            error_msg = f"Error getting balance for address {address}: {e}"
            logger.error(error_msg)
            return {'error': error_msg}

    async def _get_token_balance(self, wallet_address: str, token_contract_address: str) -> Optional[Dict]:
        """Get balance of specific token for wallet"""
        try:
            contract_address = Web3.to_checksum_address(token_contract_address)
            wallet_address = Web3.to_checksum_address(wallet_address)
            
            contract = self.web3.eth.contract(address=contract_address, abi=ERC20_ABI)
            
            # Получаем баланс
            balance = contract.functions.balanceOf(wallet_address).call()
            
            # Получаем информацию о токене
            try:
                symbol = contract.functions.symbol().call()
            except:
                symbol = "UNKNOWN"
            
            try:
                decimals = contract.functions.decimals().call()
            except:
                decimals = 18
            
            # Конвертируем баланс в правильные единицы
            balance_float = balance / (10 ** decimals)
            
            if balance_float > 0:
                return {
                    'contract': token_contract_address,
                    'balance': balance_float,
                    'symbol': symbol,
                    'decimals': decimals
                }
                
        except ContractLogicError as e:
            logger.error(f"Contract error for {token_contract_address}: {e}")
        except Exception as e:
            logger.error(f"Error getting token balance: {e}")
            
        return None

    
    async def _scan_popular_tokens(self, wallet_address: str, balance_data: Dict):
        """Scan for popular ERC-20 tokens in the wallet"""
        # Expanded list of popular token contracts (top 100+ tokens)
        popular_tokens = {
            # Stablecoins
            '0xdAC17F958D2ee523a2206206994597C13D831ec7': 'USDT',  # Tether
            '0xA0b86a33E6441e6079beB2e88B1eA0A3e9D99E9D': 'USDC',  # USD Coin
            '0x6B175474E89094C44Da98b954EedeAC495271d0F': 'DAI',   # Dai Stablecoin
            '0x4Fabb145d64652a948d72533023f6E7A623C7C53': 'BUSD',  # Binance USD
            '0x853d955aCEf822Db058eb8505911ED77F175b99e': 'FRAX',  # Frax
            '0x8E870D67F660D95d5be530380D0eC0bd388289E1': 'USDP',  # Pax Dollar
            '0x57Ab1ec28D129707052df4dF418D58a2D46d5f51': 'sUSD',  # Synth sUSD
            
            # DeFi Blue Chips
            '0x514910771AF9Ca656af840dff83E8264EcF986CA': 'LINK',  # Chainlink
            '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984': 'UNI',   # Uniswap
            '0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0': 'MATIC', # Polygon
            '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2': 'WETH',  # Wrapped Ether
            '0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599': 'WBTC',  # Wrapped Bitcoin
            '0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9': 'AAVE',  # Aave
            '0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2': 'MKR',   # Maker
            '0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F': 'SNX',   # Synthetix
            '0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e': 'YFI',   # yearn.finance
            '0x6B3595068778DD592e39A122f4f5a5cF09C90fE2': 'SUSHI', # SushiSwap
            '0x0D8775F648430679A709E98d2b0Cb6250d2887EF': 'BAT',   # Basic Attention Token
            '0xc944E90C64B2c07662A292be6244BDf05Cda44a7': 'GRT',   # The Graph
            '0x1985365e9f78359a9B6AD760e32412f4a445E862': 'REP',   # Augur
            
            # Layer 2 & Scaling
            '0x0F5D2fB29fb7d3CFeE444a200298f468908cC942': 'MANA',  # Decentraland
            '0xf629cBd94d3791C9250152BD8dfBDF380E2a3B9c': 'ENJ',   # Enjin Coin
            '0x4e15361fd6b4bb609fa63C81A2be19d873717870': 'FTX',   # FTX Token
            '0x3845badAde8e6dFF049820680d1F14bD3903a5d0': 'SAND',  # The Sandbox
            '0x0cEC1A9154Ff802e7934Fc916Ed7Ca50bDE6844e': 'POOL',  # PoolTogether
            
            # Meme & Community
            '0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE': 'SHIB',  # Shiba Inu
            '0x4d224452801ACEd8B2F0aebE155379bb5D594381': 'APE',   # ApeCoin
            '0x761D38e5ddf6ccf6Cf7c55759d5210750B5D60F3': 'ELON',  # Dogelon Mars
            '0xba2ae424d960c26247dd6c32edc70b295c744c43': 'DOGE',  # Dogecoin (wrapped)
            
            # Exchange Tokens
            '0xB8c77482e45F1F44dE1745F52C74426C631bDD52': 'BNB',   # Binance Coin
            '0x50D1c9771902476076eCFc8B2A83Ad6b9355a4c9': 'FTT',   # FTX Token
            '0x75231F58b43240C9718Dd58B4967c5114342a86c': 'OKB',   # OKB
            '0xA0b73E1Ff0B80914AB6fe0444E65848C4C34450b': 'CRO',   # Cronos
            '0x6f259637dcD74C767781E37Bc6133cd6A68aa161': 'HT',    # Huobi Token
            
            # Gaming & NFT
            '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82': 'CAKE',  # PancakeSwap
            '0x111111111117dC0aa78b770fA6A738034120C302': '1INCH', # 1inch
            '0x6810e776880C02933D47DB1b9fc05908e5386b96': 'GNO',   # Gnosis
            '0x408e41876cCCDC0F92210600ef50372656052a38': 'REN',   # Ren
            '0x8207c1FfC5B6804F6024322CcF34F29c3541Ae26': 'OGN',   # Origin Protocol
            
            # Additional Popular Tokens
            '0x3472A5A71965499acd81997a54BBA8D852C6E53d': 'BADGER', # Badger DAO
            '0xD533a949740bb3306d119CC777fa900bA034cd52': 'CRV',   # Curve DAO Token
            '0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B': 'CVX',   # Convex Finance
            '0x6B175474E89094C44Da98b954EedeAC495271d0F': 'COMP',  # Compound
            '0x0391D2021f89DC339F60Fff84546EA23E337750f': 'ARKM',  # Arkham
            '0x4Fabb145d64652a948d72533023f6E7A623C7C53': 'TUSD',  # TrueUSD
            '0x0000000000085d4780B73119b644AE5ecd22b376': 'TUSD',  # TrueUSD (old)
            '0x8E870D67F660D95d5be530380D0eC0bd388289E1': 'USDP',  # Pax Dollar
        }
        
        logger.info(f"Scanning {len(popular_tokens)} popular tokens...")
        for contract_address, symbol in popular_tokens.items():
            try:
                token_balance = await self._get_token_balance(wallet_address, contract_address)
                if token_balance and token_balance['balance'] > 0:
                    # Get ETH value for this token
                    eth_value = await self._get_token_eth_value(token_balance)
                    token_balance['eth_value'] = eth_value
                    balance_data['tokens'].append(token_balance)
                    logger.info(f"Found {symbol}: {token_balance['balance']} (~{eth_value:.6f} ETH)")
            except Exception as e:
                logger.debug(f"Error checking {symbol} token: {e}")
                continue
    
    async def _scan_tokens_via_alchemy(self, wallet_address: str, balance_data: Dict):
        """Use Alchemy SDK to get all ERC20 tokens for an address"""
        try:
            if not self.alchemy:
                raise Exception("Alchemy SDK not initialized")
            
            logger.info(f"Using Alchemy SDK to discover all tokens for {wallet_address}")
            
            # Use Alchemy SDK's getTokenBalances method
            token_balances_response = await asyncio.to_thread(
                self.alchemy.core.get_token_balances,
                wallet_address,
                "erc20"  # Get all ERC20 tokens
            )
            
            if not token_balances_response or not hasattr(token_balances_response, 'token_balances'):
                raise Exception("Invalid response from Alchemy SDK")
            
            token_balances = token_balances_response.token_balances
            logger.info(f"Alchemy SDK discovered {len(token_balances)} token contracts")
            
            # Process each token found by Alchemy
            for token_balance in token_balances:
                try:
                    contract_address = token_balance.contract_address
                    balance_hex = token_balance.token_balance
                    
                    # Skip if balance is 0 or null
                    if not balance_hex or balance_hex in ["0x0", "0x", "0x00"]:
                        continue
                    
                    # Convert hex balance to decimal
                    try:
                        balance_wei = int(balance_hex, 16)
                        if balance_wei == 0:
                            continue
                    except ValueError:
                        logger.debug(f"Invalid balance hex for {contract_address}: {balance_hex}")
                        continue
                    
                    # Get token metadata using Alchemy SDK
                    token_metadata = await asyncio.to_thread(
                        self.alchemy.core.get_token_metadata,
                        contract_address
                    )
                    
                    if not token_metadata:
                        continue
                    
                    # Calculate actual balance using decimals
                    decimals = getattr(token_metadata, 'decimals', 18) or 18
                    actual_balance = balance_wei / (10 ** decimals)
                    
                    if actual_balance <= 0:
                        continue
                    
                    # Create token data structure
                    token_data = {
                        'contract': contract_address,
                        'symbol': getattr(token_metadata, 'symbol', 'UNKNOWN') or 'UNKNOWN',
                        'name': getattr(token_metadata, 'name', 'Unknown Token') or 'Unknown Token',
                        'balance': actual_balance,
                        'decimals': decimals
                    }
                    
                    # Get ETH value
                    eth_value = await self._get_token_eth_value(token_data)
                    token_data['eth_value'] = eth_value
                    
                    # Add to results
                    balance_data['tokens'].append(token_data)
                    logger.info(f"Found {token_data['symbol']}: {actual_balance:.6f} (~{eth_value:.6f} ETH)")
                    
                except Exception as e:
                    logger.debug(f"Error processing token {contract_address}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Alchemy SDK token scan failed: {e}")
            raise
    
    

    async def _get_token_eth_value(self, token_data: Dict) -> float:
        """Get the ETH value of a token using price APIs"""
        try:
            # For WETH, return 1:1 conversion
            if token_data['symbol'].upper() == 'WETH':
                return float(token_data['balance'])
            
            # Use CoinGecko API for price data
            contract_address = token_data['contract'].lower()
            
            # Map of contract addresses to CoinGecko IDs for major tokens
            coingecko_ids = {
                '0xdac17f958d2ee523a2206206994597c13d831ec7': 'tether',
                '0xa0b86a33e6441e6079beb2e88b1ea0a3e9d99e9d': 'usd-coin',
                '0x6b175474e89094c44da98b954eedeac495271d0f': 'dai',
                '0x514910771af9ca656af840dff83e8264ecf986ca': 'chainlink',
                '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984': 'uniswap',
                '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0': 'matic-network',
                '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': 'wrapped-bitcoin',
                '0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce': 'shiba-inu',
                '0x4d224452801aced8b2f0aebe155379bb5d594381': 'apecoin',
                '0xb8c77482e45f1f44de1745f52c74426c631bdd52': 'binancecoin',
                '0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9': 'aave',
                '0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2': 'maker',
                '0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f': 'havven',
                '0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e': 'yearn-finance',
            }
            
            coingecko_id = coingecko_ids.get(contract_address)
            if not coingecko_id:
                logger.debug(f"No CoinGecko ID found for {token_data['symbol']}")
                return 0.0
            
            # Fetch price from CoinGecko
            async with aiohttp.ClientSession() as session:
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={coingecko_id}&vs_currencies=eth"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        eth_price = data.get(coingecko_id, {}).get('eth', 0)
                        total_eth_value = float(token_data['balance']) * float(eth_price)
                        return total_eth_value
                    else:
                        logger.warning(f"Failed to fetch price for {token_data['symbol']}: HTTP {response.status}")
                        return 0.0
                        
        except Exception as e:
            logger.error(f"Error getting ETH value for {token_data['symbol']}: {e}")
            return 0.0

    def get_new_transactions(self, wallet_addresses: Set[str]) -> List[Dict]:
        """Get new transactions for monitored wallets"""
        try:
            current_block = self.web3.eth.block_number

            if current_block <= self.last_checked_block:
                return []

            transactions = []
            logger.info(f"Checking blocks {self.last_checked_block + 1} to {current_block}")

            for block_num in range(self.last_checked_block + 1, current_block + 1):
                try:
                    block = self.web3.eth.get_block(block_num, full_transactions=True)

                    # Check ETH transactions
                    for tx in block.transactions:
                        tx_data = self._process_eth_transaction(tx, wallet_addresses, block)
                        if tx_data:
                            transactions.append(tx_data)

                except Exception as e:
                    logger.error(f"Error processing block {block_num}: {e}")
                    continue

            self.last_checked_block = current_block
            logger.info(f"Found {len(transactions)} new transactions")
            return transactions

        except Exception as e:
            logger.error(f"Error getting new transactions: {e}")
            return []

    def _process_eth_transaction(self, tx, wallet_addresses: Set[str], block) -> Optional[Dict]:
        """Process ETH transaction"""
        try:
            tx_from = tx['from'].lower() if tx['from'] else None
            tx_to = tx['to'].lower() if tx['to'] else None

            if tx_from in wallet_addresses or tx_to in wallet_addresses:
                wallet_address = tx_from if tx_from in wallet_addresses else tx_to
                direction = "outgoing" if tx_from in wallet_addresses else "incoming"

                return {
                    'type': 'ETH',
                    'wallet_address': wallet_address,
                    'direction': direction,
                    'from_address': tx['from'],
                    'to_address': tx['to'],
                    'amount': float(self.web3.from_wei(tx['value'], 'ether')),
                    'tx_hash': tx['hash'].hex(),
                    'block_number': block['number'],
                    'timestamp': datetime.fromtimestamp(block['timestamp']),
                    'gas_used': tx['gas'],
                    'gas_price': tx['gasPrice']
                }

        except Exception as e:
            logger.error(f"Error processing transaction: {e}")
            
        return None


class XiBot:
    """Main Xi Bot class"""

    def __init__(self, bot_token: str, web3_provider_url: str):
        self.bot_token = bot_token
        self.db = DatabaseManager()
        
        # Инициализируем монитор с проверкой ошибок
        try:
            self.monitor = TransactionMonitor(web3_provider_url)
            logger.info("✅ TransactionMonitor initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize TransactionMonitor: {e}")
            raise
        
        self.app = Application.builder().token(bot_token).build()
        self.setup_handlers()
        self.monitoring_active = False

    def setup_handlers(self):
        """Setup Telegram command handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("menu", self.menu_command))
        self.app.add_handler(CommandHandler("add_wallet", self.add_wallet_command))
        self.app.add_handler(CommandHandler("remove_wallet", self.remove_wallet_command))
        self.app.add_handler(CommandHandler("list_wallets", self.list_wallets_command))
        self.app.add_handler(CommandHandler("get_balance", self.get_balance_command))
        self.app.add_handler(CommandHandler("check_transactions", self.check_transactions_command))
        self.app.add_handler(CommandHandler("test", self.test_command))
        
        # Add callback query handler for button interactions
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """
🤖 *Xi Bot - Ethereum Wallet Monitor*

Welcome! I'll help you track your Ethereum wallet activity.

*Available Commands:*
• `/add_wallet <address> <name>` - Add a wallet to monitor
• `/remove_wallet <address>` - Remove a wallet
• `/list_wallets` - Show your tracked wallets
• `/get_balance <address>` - Get comprehensive balance with ETH values
• `/get_balance <address> <token_contract>` - Get specific token balance
• `/check_transactions` - Check for new transactions on monitored wallets
• `/test` - Test Web3 connection

*Examples:*
• `/add_wallet 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c MyMainWallet`
• `/get_balance 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c`
• `/get_balance 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c 0xdAC17F958D2ee523a2206206994597C13D831ec7`

Get started by adding your first wallet! 🚀
        """
        
        # Create interactive menu buttons
        keyboard = [
            [InlineKeyboardButton("📝 Add Wallet", callback_data="add_wallet"),
             InlineKeyboardButton("📋 My Wallets", callback_data="list_wallets")],
            [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance"),
             InlineKeyboardButton("🔄 New Transactions", callback_data="check_transactions")],
            [InlineKeyboardButton("🔧 Test Connection", callback_data="test"),
             InlineKeyboardButton("📖 Help Menu", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test Web3 connection"""
        try:
            current_block = self.monitor.web3.eth.block_number
            is_connected = self.monitor.web3.is_connected()
            
            message = f"🔌 *Connection Test:*\n"
            message += f"• Connected: {'✅' if is_connected else '❌'}\n"
            message += f"• Current block: {current_block}\n"
            message += f"• Provider: {self.monitor.web3_provider_url}\n"
            
            # Test with a known address
            test_address = "0x742d35cc6634c0532925a3b8d17319244f6c7f9c"
            try:
                balance_wei = self.monitor.web3.eth.get_balance(test_address)
                balance_eth = self.monitor.web3.from_wei(balance_wei, 'ether')
                message += f"• Test balance: {float(balance_eth):.6f} ETH\n"
            except Exception as e:
                message += f"• Test balance: Error - {e}\n"
            
            await self._safe_send_message(update, message)
            
        except Exception as e:
            await self._safe_send_message(update, f"❌ Connection test failed: {e}")

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display interactive menu"""
        keyboard = [
            [InlineKeyboardButton("📝 Add Wallet", callback_data="add_wallet"),
             InlineKeyboardButton("📋 My Wallets", callback_data="list_wallets")],
            [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance"),
             InlineKeyboardButton("🔄 New Transactions", callback_data="check_transactions")],
            [InlineKeyboardButton("🔧 Test Connection", callback_data="test"),
             InlineKeyboardButton("📖 Help Menu", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🤖 **Xi Bot Main Menu**\n\nChoose an action:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "add_wallet":
            await self._safe_edit_message(
                query,
                "📝 **Add New Wallet**\n\n"
                "To add a wallet, use this command:\n"
                "`/add_wallet <address> <name>`\n\n"
                "**Example:**\n"
                "`/add_wallet 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c MyMainWallet`",
                reply_markup=self._get_back_to_menu_keyboard()
            )
            
        elif data == "list_wallets":
            wallets = self.db.get_user_wallets(user_id)
            if not wallets:
                await self._safe_edit_message(
                    query,
                    "📭 **No Wallets Found**\n\n"
                    "You don't have any wallets added yet!\n"
                    "Use the Add Wallet button to add your first wallet.",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
            else:
                message = "💼 **Your Tracked Wallets:**\n\n"
                keyboard = []
                
                for i, wallet in enumerate(wallets, 1):
                    message += f"{i}. **{wallet['name']}**\n"
                    message += f"   `{wallet['address']}`\n\n"
                    
                    # Add button for each wallet to check balance
                    keyboard.append([InlineKeyboardButton(
                        f"💰 {wallet['name']} Balance", 
                        callback_data=f"balance_{wallet['address']}"
                    )])
                
                message += f"Total: {len(wallets)} wallet(s) monitored 📊"
                
                keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await self._safe_edit_message(
                    query,
                    message,
                    reply_markup=reply_markup
                )
                
        elif data == "check_balance":
            wallets = self.db.get_user_wallets(user_id)
            if not wallets:
                await self._safe_edit_message(
                    query,
                    "📭 **No Wallets to Check**\n\n"
                    "Add a wallet first to check balances!",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
            else:
                keyboard = []
                for wallet in wallets:
                    keyboard.append([InlineKeyboardButton(
                        f"💰 {wallet['name']}", 
                        callback_data=f"balance_{wallet['address']}"
                    )])
                
                keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await self._safe_edit_message(
                    query,
                    "💰 **Select Wallet to Check Balance:**",
                    reply_markup=reply_markup
                )
                
        elif data.startswith("balance_"):
            wallet_address = data.replace("balance_", "")
            await self._safe_edit_message(
                query,
                "⏳ **Fetching Balance Data...**\n\n"
                f"Getting comprehensive balance for:\n`{self._escape_markdown(wallet_address)}`"
            )
            
            # Get balance data
            balance_data = await self.monitor.get_address_balance(wallet_address, scan_all_tokens=True)
            
            if balance_data.get('error'):
                await self._safe_edit_message(
                    query,
                    f"❌ **Error Getting Balance**\n\n{self._escape_markdown(str(balance_data['error']))}",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
                return
            
            # Format balance message
            total_token_eth_value = sum(token.get('eth_value', 0) for token in balance_data['tokens'])
            total_portfolio_eth = balance_data['eth_balance'] + total_token_eth_value
            sorted_tokens = sorted(balance_data['tokens'], key=lambda x: x.get('eth_value', 0), reverse=True)
            
            message = f"💰 **Balance Summary**\n\n"
            message += f"**ETH:** {balance_data['eth_balance']:.6f} ETH\n"
            message += f"**Tokens:** {balance_data['token_count']} types\n"
            message += f"**Token Value:** {total_token_eth_value:.6f} ETH\n"
            message += f"**🎯 Total Portfolio:** {total_portfolio_eth:.6f} ETH\n\n"
            
            if sorted_tokens:
                top_tokens = sorted_tokens[:3]  # Show top 3 for button view
                message += "**Top Tokens:**\n"
                for token in top_tokens:
                    eth_value = token.get('eth_value', 0)
                    message += f"• {token['symbol']}: ~{eth_value:.6f} ETH\n"
                
                if len(sorted_tokens) > 3:
                    remaining = len(sorted_tokens) - 3
                    message += f"• +{remaining} more tokens\n"
            
            keyboard = [
                [InlineKeyboardButton("🔍 Full Details", callback_data=f"full_balance_{wallet_address}")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self._safe_edit_message(
                query,
                message,
                reply_markup=reply_markup
            )
            
        elif data.startswith("full_balance_"):
            wallet_address = data.replace("full_balance_", "")
            # Send full balance as new message to avoid telegram message length limits
            balance_data = await self.monitor.get_address_balance(wallet_address, scan_all_tokens=True)
            
            if balance_data.get('error'):
                await query.message.reply_text(f"❌ Error: {balance_data['error']}")
                return
            
            # Use the existing detailed balance format
            total_token_eth_value = sum(token.get('eth_value', 0) for token in balance_data['tokens'])
            total_portfolio_eth = balance_data['eth_balance'] + total_token_eth_value
            sorted_tokens = sorted(balance_data['tokens'], key=lambda x: x.get('eth_value', 0), reverse=True)
            
            message = f"💰 **Full Balance for `{wallet_address}`**\n\n"
            message += f"**ETH Balance:** {balance_data['eth_balance']:.6f} ETH\n"
            
            if balance_data['tokens']:
                message += f"\n**Tokens Found:** {balance_data['token_count']}\n"
                message += f"**Total Token Value:** {total_token_eth_value:.6f} ETH\n\n"
                
                top_tokens = sorted_tokens[:5] if len(sorted_tokens) >= 5 else sorted_tokens
                if len(sorted_tokens) >= 5:
                    message += "**Top 5 Most Valuable Tokens:**\n"
                else:
                    message += "**Token Balances:**\n"
                    
                for i, token in enumerate(top_tokens, 1):
                    if token['balance'] >= 1:
                        balance_str = f"{token['balance']:.2f}"
                    elif token['balance'] >= 0.01:
                        balance_str = f"{token['balance']:.4f}"
                    else:
                        balance_str = f"{token['balance']:.8f}"
                    
                    eth_value = token.get('eth_value', 0)
                    if len(sorted_tokens) >= 5:
                        message += f"{i}. **{token['symbol']}:** {balance_str} (~{eth_value:.6f} ETH)\n"
                    else:
                        message += f"• **{token['symbol']}:** {balance_str} (~{eth_value:.6f} ETH)\n"
                        
                if len(sorted_tokens) > 5:
                    remaining_count = len(sorted_tokens) - 5
                    remaining_value = sum(token.get('eth_value', 0) for token in sorted_tokens[5:])
                    message += f"\n*+{remaining_count} more tokens (~{remaining_value:.6f} ETH)*\n"
            else:
                message += f"\n**Tokens Found:** 0\n"
                message += "**Note:** No popular tokens detected\n"
            
            message += f"\n**Portfolio Summary:**\n"
            message += f"• ETH Balance: {balance_data['eth_balance']:.6f} ETH\n"
            message += f"• Token Value: {total_token_eth_value:.6f} ETH\n"
            message += f"• **Total Portfolio: {total_portfolio_eth:.6f} ETH**\n"
            message += f"• Token Types: {balance_data['token_count']}\n"
            
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            
        elif data == "check_transactions":
            await self._handle_check_transactions_callback(query, user_id)
            
        elif data == "test":
            try:
                current_block = self.monitor.web3.eth.block_number
                is_connected = self.monitor.web3.is_connected()
                
                message = f"🔌 **Connection Test Results:**\n\n"
                message += f"• Status: {'✅ Connected' if is_connected else '❌ Disconnected'}\n"
                message += f"• Current Block: {current_block}\n"
                message += f"• Provider: Ethereum Mainnet\n"
                
                await self._safe_edit_message(
                    query,
                    message,
                    reply_markup=self._get_back_to_menu_keyboard()
                )
            except Exception as e:
                await self._safe_edit_message(
                    query,
                    f"❌ **Connection Test Failed**\n\n{self._escape_markdown(str(e))}",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
                
        elif data == "help":
            help_message = """
📖 **Xi Bot Help Guide**

**Commands:**
• `/start` - Show main menu
• `/menu` - Display interactive menu
• `/add_wallet <address> <name>` - Add wallet
• `/list_wallets` - Show your wallets
• `/get_balance <address>` - Get balance
• `/check_transactions` - Check new transactions
• `/test` - Test connection

**Features:**
• 🔄 Real-time transaction monitoring
• 💰 Comprehensive balance checking
• 📊 ETH value calculations for tokens
• 🏆 Top 5 most valuable tokens display
• 📱 Interactive button interface

**Support:**
Use the menu buttons for easy navigation!
            """
            
            await self._safe_edit_message(
                query,
                help_message,
                reply_markup=self._get_back_to_menu_keyboard()
            )
            
        elif data == "menu":
            keyboard = [
                [InlineKeyboardButton("📝 Add Wallet", callback_data="add_wallet"),
                 InlineKeyboardButton("📋 My Wallets", callback_data="list_wallets")],
                [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance"),
                 InlineKeyboardButton("🔄 New Transactions", callback_data="check_transactions")],
                [InlineKeyboardButton("🔧 Test Connection", callback_data="test"),
                 InlineKeyboardButton("📖 Help Menu", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self._safe_edit_message(
                query,
                "🤖 **Xi Bot Main Menu**\n\nChoose an action:",
                reply_markup=reply_markup
            )

    def _get_back_to_menu_keyboard(self):
        """Get back to menu keyboard"""
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]])

    async def _safe_edit_message(self, query, message: str, reply_markup=None):
        """Safely edit message with fallback for markdown parsing errors"""
        try:
            await query.edit_message_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except BadRequest as e:
            if "can't parse entities" in str(e).lower():
                logger.warning(f"Markdown parsing failed, sending as plain text: {e}")
                # Remove markdown formatting and send as plain text
                plain_message = message.replace('**', '').replace('`', '').replace('*', '').replace('_', '')
                await query.edit_message_text(
                    plain_message,
                    reply_markup=reply_markup
                )
            else:
                raise

    async def _handle_check_transactions_callback(self, query, user_id):
        """Handle check transactions callback"""
        try:
            user_wallets = self.db.get_user_wallets(user_id)
            
            if not user_wallets:
                await self._safe_edit_message(
                    query,
                    "📭 **No Wallets to Monitor**\n\n"
                    "Add a wallet first to check for transactions!",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
                return
            
            await self._safe_edit_message(
                query,
                "🔍 **Checking for New Transactions...**\n\n"
                f"Scanning {len(user_wallets)} wallet(s) for recent activity..."
            )
            
            # Get all wallets for monitoring
            wallet_users = self.db.get_all_wallets()
            wallet_addresses = set(wallet_users.keys())
            
            # Check for new transactions
            transactions = self.monitor.get_new_transactions(wallet_addresses)
            
            if not transactions:
                await self._safe_edit_message(
                    query,
                    "✅ **Transaction Check Complete**\n\n"
                    f"No new transactions found since last check.\n"
                    f"Monitoring {len(user_wallets)} wallet(s).",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
                return
            
            # Filter transactions for this user's wallets
            user_wallet_addresses = {wallet['address'].lower() for wallet in user_wallets}
            user_transactions = [tx for tx in transactions if tx['wallet_address'] in user_wallet_addresses]
            
            if not user_transactions:
                await self._safe_edit_message(
                    query,
                    f"✅ **Transaction Check Complete**\n\n"
                    f"Found {len(transactions)} new transaction(s) on the network, "
                    f"but none for your {len(user_wallets)} monitored wallet(s).",
                    reply_markup=self._get_back_to_menu_keyboard()
                )
                return
            
            # Send summary
            await self._safe_edit_message(
                query,
                f"🎯 **New Transactions Found!**\n\n"
                f"Found {len(user_transactions)} new transaction(s) for your wallets.\n"
                f"Sending detailed notifications...",
                reply_markup=self._get_back_to_menu_keyboard()
            )
            
            # Send individual transaction notifications
            for tx in user_transactions:
                wallet_name = self.db.get_wallet_name(user_id, tx['wallet_address'])
                if wallet_name:
                    await self.send_transaction_notification(user_id, wallet_name, tx)
                    
        except Exception as e:
            logger.error(f"Error in _handle_check_transactions_callback: {e}")
            await self._safe_edit_message(
                query,
                f"❌ **Error Checking Transactions**\n\n{self._escape_markdown(str(e))}",
                reply_markup=self._get_back_to_menu_keyboard()
            )

    async def add_wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_wallet command"""
        user_id = update.effective_user.id

        if len(context.args) < 2:
            await self._safe_send_message(update,
                "❌ Usage: `/add_wallet <address> <name>`\n\n"
                "Example: `/add_wallet 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c MyWallet`")
            return

        wallet_address = context.args[0]
        wallet_name = " ".join(context.args[1:])

        if not self.monitor.is_valid_address(wallet_address):
            await update.message.reply_text("❌ Invalid Ethereum address format!")
            return

        wallet_address = self.monitor.format_address(wallet_address)

        if self.db.add_wallet(user_id, wallet_address, wallet_name):
            await self._safe_send_message(update,
                f"✅ Wallet added successfully!\n\n"
                f"**Name:** {self._escape_markdown(wallet_name)}\n"
                f"**Address:** `{wallet_address}`\n\n"
                f"I'll notify you of all transactions on this wallet! 📱")
        else:
            await update.message.reply_text("❌ Wallet already exists in your list!")

    async def remove_wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /remove_wallet command"""
        user_id = update.effective_user.id

        if len(context.args) != 1:
            await self._safe_send_message(update,
                "❌ Usage: `/remove_wallet <address>`\n\n"
                "Example: `/remove_wallet 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c`")
            return

        wallet_address = context.args[0]

        if not self.monitor.is_valid_address(wallet_address):
            await update.message.reply_text("❌ Invalid Ethereum address format!")
            return

        wallet_address = self.monitor.format_address(wallet_address)

        if self.db.remove_wallet(user_id, wallet_address):
            await self._safe_send_message(update,
                f"✅ Wallet removed successfully!\n\n"
                f"**Address:** `{wallet_address}`\n\n"
                f"I'll no longer monitor this wallet for you.")
        else:
            await update.message.reply_text("❌ Wallet not found in your list!")

    async def list_wallets_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_wallets command"""
        user_id = update.effective_user.id
        wallets = self.db.get_user_wallets(user_id)

        if not wallets:
            await self._safe_send_message(update,
                "📭 You don't have any wallets added yet!\n\n"
                "Use `/add_wallet <address> <name>` to add your first wallet.")
            return

        message = "💼 **Your Tracked Wallets:**\n\n"

        for i, wallet in enumerate(wallets, 1):
            message += f"{i}. **{self._escape_markdown(wallet['name'])}**\n"
            message += f"   `{wallet['address']}`\n\n"

        message += f"Total: {len(wallets)} wallet(s) monitored 📊"

        await self._safe_send_message(update, message)

    async def get_balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /get_balance command"""
        if len(context.args) not in [1, 2]:
            await self._safe_send_message(update,
                "❌ Usage: `/get_balance <address> [token_contract]`\n\n"
                "Examples:\n"
                "• `/get_balance 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c` (Full balance scan)\n"
                "• `/get_balance 0x742d35Cc6634C0532925a3b8D17319244F6C7F9c 0xdAC17F958D2ee523a2206206994597C13D831ec7` (Specific token)")
            return

        wallet_address = context.args[0]
        token_contract_address = context.args[1] if len(context.args) == 2 else None

        if not self.monitor.is_valid_address(wallet_address):
            await update.message.reply_text("❌ Invalid wallet address format!")
            return

        if token_contract_address and not self.monitor.is_valid_address(token_contract_address):
            await update.message.reply_text("❌ Invalid token contract address format!")
            return

        wallet_address = self.monitor.format_address(wallet_address)
        if token_contract_address:
            token_contract_address = self.monitor.format_address(token_contract_address)

        await update.message.reply_text("⏳ Fetching balance data...")

        # If no specific token is requested, scan for popular tokens
        scan_all = token_contract_address is None
        balance_data = await self.monitor.get_address_balance(wallet_address, token_contract_address, scan_all_tokens=scan_all)

        if balance_data.get('error'):
            await self._safe_send_message(update, f"❌ Error: {balance_data['error']}")
            return

        # Format balance message with improved display
        message = f"💰 **Balance for `{wallet_address}`**\n\n"
        message += f"**ETH Balance:** {balance_data['eth_balance']:.6f} ETH\n"
        
        # Calculate total portfolio value in ETH
        total_token_eth_value = sum(token.get('eth_value', 0) for token in balance_data['tokens'])
        total_portfolio_eth = balance_data['eth_balance'] + total_token_eth_value
        
        # Sort tokens by ETH value (highest first)
        sorted_tokens = sorted(balance_data['tokens'], key=lambda x: x.get('eth_value', 0), reverse=True)
        
        # Display token information
        if balance_data['tokens']:
            message += f"\n**Tokens Found:** {balance_data['token_count']}\n"
            message += f"**Total Token Value:** {total_token_eth_value:.6f} ETH\n\n"
            
            # Show top 5 most valuable tokens
            top_tokens = sorted_tokens[:5] if len(sorted_tokens) >= 5 else sorted_tokens
            if len(sorted_tokens) >= 5:
                message += "**Top 5 Most Valuable Tokens:**\n"
            else:
                message += "**Token Balances:**\n"
                
            for i, token in enumerate(top_tokens, 1):
                # Format token balance with appropriate decimal places
                if token['balance'] >= 1:
                    balance_str = f"{token['balance']:.2f}"
                elif token['balance'] >= 0.01:
                    balance_str = f"{token['balance']:.4f}"
                else:
                    balance_str = f"{token['balance']:.8f}"
                
                eth_value = token.get('eth_value', 0)
                if len(sorted_tokens) >= 5:
                    message += f"{i}. **{self._escape_markdown(token['symbol'])}:** {balance_str} (~{eth_value:.6f} ETH)\n"
                else:
                    message += f"• **{self._escape_markdown(token['symbol'])}:** {balance_str} (~{eth_value:.6f} ETH)\n"
                    
            # Show remaining tokens count if more than 5
            if len(sorted_tokens) > 5:
                remaining_count = len(sorted_tokens) - 5
                remaining_value = sum(token.get('eth_value', 0) for token in sorted_tokens[5:])
                message += f"\n*+{remaining_count} more tokens (~{remaining_value:.6f} ETH)*\n"
        else:
            message += f"\n**Tokens Found:** 0\n"
            if not token_contract_address:
                message += "**Note:** No popular tokens detected\n"
            else:
                message += "**Note:** Specified token has zero balance\n"

        # Add comprehensive summary
        message += f"\n**Portfolio Summary:**\n"
        message += f"• ETH Balance: {balance_data['eth_balance']:.6f} ETH\n"
        message += f"• Token Value: {total_token_eth_value:.6f} ETH\n"
        message += f"• **Total Portfolio: {total_portfolio_eth:.6f} ETH**\n"
        message += f"• Token Types: {balance_data['token_count']}\n"

        await self._safe_send_message(update, message)

    async def check_transactions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /check_transactions command - manually check for new transactions"""
        user_id = update.effective_user.id
        
        await update.message.reply_text("🔍 Checking for new transactions on your monitored wallets...")
        
        try:
            # Get user's wallets
            user_wallets = self.db.get_user_wallets(user_id)
            
            if not user_wallets:
                await self._safe_send_message(update,
                    "📭 You don't have any wallets added yet!\n\n"
                    "Use `/add_wallet <address> <name>` to add your first wallet.")
                return
            
            # Get all wallets for monitoring
            wallet_users = self.db.get_all_wallets()
            wallet_addresses = set(wallet_users.keys())
            
            # Check for new transactions
            transactions = self.monitor.get_new_transactions(wallet_addresses)
            
            if not transactions:
                await self._safe_send_message(update,
                    "✅ **Transaction Check Complete**\n\n"
                    f"No new transactions found since last check.\n"
                    f"Monitoring {len(user_wallets)} wallet(s) for user.")
                return
            
            # Filter transactions for this user's wallets
            user_wallet_addresses = {wallet['address'].lower() for wallet in user_wallets}
            user_transactions = [tx for tx in transactions if tx['wallet_address'] in user_wallet_addresses]
            
            if not user_transactions:
                await self._safe_send_message(update,
                    f"✅ **Transaction Check Complete**\n\n"
                    f"Found {len(transactions)} new transaction(s) on the network, "
                    f"but none for your {len(user_wallets)} monitored wallet(s).")
                return
            
            # Send summary first
            await self._safe_send_message(update,
                f"🎯 **New Transactions Found!**\n\n"
                f"Found {len(user_transactions)} new transaction(s) for your wallets:")
            
            # Send individual transaction notifications
            for tx in user_transactions:
                wallet_name = self.db.get_wallet_name(user_id, tx['wallet_address'])
                if wallet_name:
                    await self.send_transaction_notification(user_id, wallet_name, tx)
                    
        except Exception as e:
            logger.error(f"Error in check_transactions_command: {e}")
            await self._safe_send_message(update, f"❌ Error checking transactions: {e}")

    async def send_transaction_notification(self, user_id: int, wallet_name: str, tx_data: Dict):
        """Send transaction notification to user"""
        try:
            message = self._format_eth_notification(wallet_name, tx_data)

            try:
                await self.app.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
            except BadRequest as e:
                if "can't parse entities" in str(e).lower():
                    logger.warning(f"Markdown parsing failed for user {user_id}, sending as plain text: {e}")
                    plain_message = message.replace('**', '').replace('`', '').replace('*', '').replace('_', '')
                    await self.app.bot.send_message(
                        chat_id=user_id,
                        text=plain_message,
                        disable_web_page_preview=True
                    )
                else:
                    raise
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")

    def _escape_markdown(self, text: str) -> str:
        """Escape special characters for Telegram MarkdownV1"""
        if not text:
            return text
        chars_to_escape = ['*', '_', '`', '[', ']']
        escaped_text = text
        for char in chars_to_escape:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        return escaped_text

    async def _safe_send_message(self, update, message, parse_markdown=True):
        """Send message with fallback to plain text if markdown parsing fails"""
        try:
            if parse_markdown:
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(message)
        except BadRequest as e:
            if "can't parse entities" in str(e).lower():
                logger.warning(f"Markdown parsing failed, sending as plain text: {e}")
                plain_message = message.replace('**', '').replace('`', '').replace('*', '').replace('_', '')
                await update.message.reply_text(plain_message)
            else:
                raise

    def _format_eth_notification(self, wallet_name: str, tx_data: Dict) -> str:
        """Format ETH transaction notification"""
        direction_icon = "📤" if tx_data['direction'] == 'outgoing' else "📥"
        direction_text = "Sent" if tx_data['direction'] == 'outgoing' else "Received"

        message = f"{direction_icon} **ETH Transaction - {self._escape_markdown(wallet_name)}**\n\n"
        message += f"**Type:** {direction_text} ETH\n"
        message += f"**Amount:** {tx_data['amount']:.6f} ETH\n"
        message += f"**From:** `{tx_data['from_address']}`\n"
        message += f"**To:** `{tx_data['to_address']}`\n"
        message += f"**Time:** {tx_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        message += f"**Hash:** `{tx_data['tx_hash']}`\n"
        message += f"**Block:** {tx_data['block_number']}"

        return message

    async def monitor_transactions(self):
        """Main monitoring loop - runs every 10 seconds"""
        while self.monitoring_active:
            try:
                wallet_users = self.db.get_all_wallets()

                if not wallet_users:
                    await asyncio.sleep(10)
                    continue

                wallet_addresses = set(wallet_users.keys())
                transactions = self.monitor.get_new_transactions(wallet_addresses)

                for tx in transactions:
                    wallet_addr = tx['wallet_address']
                    user_ids = wallet_users.get(wallet_addr, [])

                    for user_id in user_ids:
                        wallet_name = self.db.get_wallet_name(user_id, wallet_addr)
                        if wallet_name:
                            await self.send_transaction_notification(user_id, wallet_name, tx)

                if transactions:
                    logger.info(f"Processed {len(transactions)} new transactions")

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")

            await asyncio.sleep(10)

    async def start(self):
        """Start the bot"""
        logger.info("Starting Xi Bot...")

        self.monitoring_active = True
        monitor_task = asyncio.create_task(self.monitor_transactions())

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()

        logger.info("Xi Bot is running!")

        try:
            await monitor_task
        except KeyboardInterrupt:
            logger.info("Shutting down Xi Bot...")
            self.monitoring_active = False

        finally:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()


def validate_configuration():
    """Validate required configuration and provide helpful error messages"""
    errors = []
    warnings = []

    # Check Telegram Bot Token
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        errors.append("TELEGRAM_BOT_TOKEN is required. Get one from @BotFather on Telegram.")
    elif not bot_token.startswith(('1', '2', '5', '6', '7')):  # Basic bot token format check
        warnings.append("TELEGRAM_BOT_TOKEN format seems invalid. Bot tokens typically start with digits 1,2,5,6,7.")

    # Check Web3 Provider URL
    web3_url = os.getenv("WEB3_PROVIDER_URL")
    if not web3_url:
        errors.append("WEB3_PROVIDER_URL is required. Use services like Alchemy, Infura, or QuickNode.")
    elif "YOUR_API_KEY" in web3_url or "your_endpoint" in web3_url.lower():
        errors.append("WEB3_PROVIDER_URL contains placeholder text. Please set a real Ethereum node URL.")
    elif not (web3_url.startswith("https://") or web3_url.startswith("wss://")):
        warnings.append("WEB3_PROVIDER_URL should typically start with https:// or wss://")

    return errors, warnings


def setup_logging():
    """Setup logging configuration"""
    debug = os.getenv("DEBUG", "false").lower() == "true"
    level = logging.DEBUG if debug else logging.INFO

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=level,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('xi_bot.log', encoding='utf-8')
        ]
    )

    # Reduce noise from some libraries
    if not debug:
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('telegram').setLevel(logging.WARNING)


def display_banner():
    """Display startup banner"""
    banner = """
╔══════════════════════════════════════════════╗
║                   Xi Bot                     ║
║        Ethereum Wallet Activity Monitor     ║
║                                              ║
║  🔗 Tracks ETH, ERC-20 & NFT transactions   ║
║  📱 Telegram notifications                   ║
║  ⚡ Real-time monitoring                     ║
╚══════════════════════════════════════════════╝
    """
    print(banner)


def load_environment():
    """Load environment variables from .env file if available"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("Warning: python-dotenv not installed. Environment variables must be set manually.")


async def main():
    """Main function to run the bot"""
    display_banner()
    
    # Load environment variables
    load_environment()
    
    # Setup logging
    setup_logging()
    
    # Validate configuration
    errors, warnings = validate_configuration()

    # Display warnings
    if warnings:
        print("⚠️  Configuration Warnings:")
        for warning in warnings:
            print(f"   • {warning}")
        print()

    # Check for errors
    if errors:
        print("❌ Configuration Errors:")
        for error in errors:
            print(f"   • {error}")
        print()
        print("Please fix the above errors and try again.")
        sys.exit(1)

    print("✅ Configuration validated successfully!")
    print()

    # Get configuration
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    WEB3_PROVIDER_URL = os.getenv("WEB3_PROVIDER_URL")

    try:
        print("🚀 Starting Xi Bot...")
        bot = XiBot(BOT_TOKEN, WEB3_PROVIDER_URL)
        await bot.start()
    except KeyboardInterrupt:
        print("\n⏹️  Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Fatal error starting bot: {e}")
        print(f"\n❌ Fatal error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check your internet connection")
        print("2. Verify your WEB3_PROVIDER_URL is working")
        print("3. Ensure your TELEGRAM_BOT_TOKEN is correct")
        print("4. Check the log file (xi_bot.log) for more details")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import sys
        sys.exit(1)
