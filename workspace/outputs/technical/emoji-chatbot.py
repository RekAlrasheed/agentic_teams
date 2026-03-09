#!/usr/bin/env python3
"""
Emoji-Only Chatbot
A delightfully limited AI that communicates exclusively in emojis.
Perfect for when words just aren't enough... because they're not allowed.
"""

import random
from typing import Dict, List


class EmojiChatbot:
    """A chatbot that speaks only in emojis."""

    def __init__(self):
        """Initialize the chatbot with emoji response mappings."""
        # Comprehensive emoji mapping for common inputs
        self.emoji_map: Dict[str, List[str]] = {
            # Greetings
            "hello": ["👋", "😊", "🎉"],
            "hi": ["👋", "😄", "🙌"],
            "hey": ["👋", "😎", "🤙"],
            "good morning": ["🌅", "☀️", "😊", "👋"],
            "good night": ["🌙", "😴", "💤", "👋"],

            # Feelings & Emotions
            "happy": ["😊", "😄", "🥳", "✨"],
            "sad": ["😢", "😭", "💔", "😞"],
            "angry": ["😠", "🤬", "💥", "😤"],
            "confused": ["🤔", "❓", "😕", "🤷"],
            "tired": ["😴", "💤", "🥱", "😩"],
            "excited": ["🎉", "🥳", "🤩", "⚡"],
            "love": ["❤️", "💕", "😍", "💑"],
            "scared": ["😨", "👻", "😱", "😰"],

            # Food & Drink
            "hungry": ["🍔", "🍕", "😋", "🍽️"],
            "pizza": ["🍕", "😍", "🤤", "😋"],
            "coffee": ["☕", "😴", "⚡", "🤎"],
            "beer": ["🍺", "😎", "🎉", "🍻"],
            "food": ["🍽️", "😋", "🤤", "👨‍🍳"],
            "eat": ["😋", "🍴", "🤤", "😋"],

            # Work & Productivity
            "work": ["💼", "😩", "⏰", "💻"],
            "code": ["💻", "⌨️", "🤓", "✨"],
            "bug": ["🐛", "💥", "🔥", "😤"],
            "meeting": ["📅", "😴", "☕", "💤"],
            "deadline": ["⏰", "😱", "🔥", "💨"],
            "help": ["🆘", "🤝", "💪", "🚀"],

            # Activities
            "play": ["🎮", "🎯", "🏃", "😄"],
            "sleep": ["😴", "🛏️", "💤", "🌙"],
            "party": ["🎉", "🎊", "🥳", "🎈"],
            "dance": ["💃", "🕺", "🎵", "🎶"],
            "run": ["🏃", "💨", "⚡", "🏁"],
            "swim": ["🏊", "🌊", "😎", "☀️"],

            # Social
            "friend": ["👫", "🤝", "💪", "😊"],
            "family": ["👨‍👩‍👧‍👦", "❤️", "🏠", "😊"],
            "kiss": ["😘", "💋", "😍", "💕"],
            "fight": ["👊", "💥", "😠", "⚔️"],
            "talk": ["💬", "🗣️", "👂", "💭"],

            # Technology
            "phone": ["📱", "🔋", "😤", "📲"],
            "computer": ["💻", "🖥️", "⌨️", "🖱️"],
            "internet": ["🌐", "📡", "⚡", "🔌"],
            "wifi": ["📶", "⚡", "😤", "🔌"],
            "video": ["🎥", "📹", "🎬", "👀"],

            # Nature & Weather
            "rain": ["🌧️", "💧", "☔", "😔"],
            "sun": ["☀️", "🌞", "😎", "🏖️"],
            "snow": ["❄️", "⛄", "🥶", "☃️"],
            "hot": ["🔥", "😅", "💦", "☀️"],
            "cold": ["🥶", "❄️", "🧊", "😫"],
            "beach": ["🏖️", "🌊", "😎", "☀️"],
            "mountain": ["⛰️", "🏔️", "👣", "🎽"],

            # Sports & Games
            "football": ["🏈", "⚽", "🏃", "🎯"],
            "basketball": ["🏀", "🏃", "⚡", "🏆"],
            "tennis": ["🎾", "👊", "⚡", "🏆"],
            "win": ["🏆", "🥇", "🎉", "👑"],
            "lose": ["😭", "💔", "😞", "2️⃣"],

            # Time & Dates
            "morning": ["🌅", "☀️", "😴", "☕"],
            "afternoon": ["🌤️", "☀️", "😊", "☕"],
            "evening": ["🌆", "🌅", "😌", "☕"],
            "night": ["🌙", "⭐", "😴", "💤"],
            "today": ["📅", "⏰", "🎯", "📍"],
            "tomorrow": ["📅", "⏩", "🎯", "🚀"],
            "weekend": ["🎉", "😎", "🏖️", "☀️"],

            # Animals
            "dog": ["🐕", "🐶", "❤️", "🦴"],
            "cat": ["🐱", "🐈", "😸", "🧶"],
            "monkey": ["🐵", "🐒", "🍌", "😄"],
            "bird": ["🐦", "✈️", "🪶", "🎵"],
            "shark": ["🦈", "😱", "🌊", "⚠️"],

            # Money & Value
            "money": ["💰", "💵", "💳", "😊"],
            "rich": ["💰", "💎", "👑", "🤑"],
            "poor": ["😢", "💸", "😞", "🤷"],
            "expensive": ["💸", "😱", "💰", "😩"],
            "cheap": ["💰", "😊", "✨", "🎯"],

            # Math & Numbers
            "one": ["1️⃣", "☝️", "👆", "🎯"],
            "two": ["2️⃣", "✌️", "👉👈", "🎯"],
            "three": ["3️⃣", "🤟", "👉👉👉", "🎯"],
            "zero": ["0️⃣", "🍩", "🙅", "❌"],
            "math": ["🧮", "📐", "🤓", "📊"],
            "count": ["1️⃣", "2️⃣", "3️⃣", "📊"],

            # Luck & Fortune
            "luck": ["🍀", "🎰", "🎲", "✨"],
            "magic": ["✨", "🪄", "🎩", "🌟"],
            "wish": ["🪄", "⭐", "🎊", "💫"],
            "wish": ["🪄", "⭐", "🎊", "💫"],

            # Opinions
            "good": ["👍", "✨", "🎉", "💯"],
            "bad": ["👎", "😞", "💔", "😤"],
            "ok": ["👌", "😐", "🤷", "⚖️"],
            "amazing": ["🤩", "✨", "🎉", "🏆"],
            "terrible": ["😤", "💔", "😠", "💥"],

            # Default responses for unmapped inputs
            "why": ["🤔", "❓", "🤷", "😕"],
            "what": ["❓", "🤷", "🤔", "❗"],
            "when": ["⏰", "📅", "❓", "⏩"],
            "where": ["📍", "🗺️", "🧭", "❓"],
            "how": ["❓", "🤔", "💭", "🤷"],
        }

    def process_input(self, user_input: str) -> str:
        """
        Convert user input to emoji response.

        Args:
            user_input: User's text message

        Returns:
            String of emojis representing the response
        """
        # Normalize input
        user_input = user_input.lower().strip()

        # Remove punctuation for better matching
        clean_input = ''.join(c for c in user_input if c.isalnum() or c.isspace())

        # Try exact word matches first
        for word in clean_input.split():
            if word in self.emoji_map:
                return self._generate_response(word)

        # Try phrase matches
        for phrase in self.emoji_map.keys():
            if phrase in clean_input:
                return self._generate_response(phrase)

        # If no match found, respond with confusion or encouragement
        return self._generate_default_response()

    def _generate_response(self, matched_keyword: str) -> str:
        """Generate an emoji response for a matched keyword."""
        emojis = self.emoji_map[matched_keyword]

        # Sometimes respond with 1-3 emojis, sometimes 4-6
        response_length = random.choice([1, 2, 3, 4, 5])
        response = [random.choice(emojis) for _ in range(response_length)]

        # Occasionally add a reaction emoji at the end
        if random.random() > 0.6:
            response.extend([random.choice(["👆", "💯", "🎯", "✨"])])

        return "".join(response)

    def _generate_default_response(self) -> str:
        """Generate a response for unmatched input."""
        default_reactions = [
            "🤔❓🤷",  # Confusion
            "😕💭❓",  # Pondering
            "❗🤨❓",  # Questioning
            "👀💭✨",  # Intrigued
            "🎲🤪😄",  # Random enthusiasm
            "😊🤷✨",  # Neutral friendliness
            "🔮🤔❓",  # Mysterious
            "👂💬🎯",  # Listening
        ]
        return random.choice(default_reactions)

    def chat(self):
        """Interactive chat mode."""
        print("\n" + "="*50)
        print("🤖 EMOJI CHATBOT 🤖")
        print("="*50)
        print("\n😊 Hello! I speak only in emojis. Type something!\n")
        print("(Type 'quit' to exit)\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    print("Bot: 👂💬✨\n")
                    continue

                if user_input.lower() in ["quit", "exit", "bye"]:
                    print("Bot: 👋😊💕✨\n")
                    print("Goodbye! 👋\n")
                    break

                response = self.process_input(user_input)
                print(f"Bot: {response}\n")

            except KeyboardInterrupt:
                print("\n\nBot: 👋😊✨\n")
                break
            except Exception as e:
                print(f"Bot: 😱❌❓\n")


def demo_conversations():
    """Run some entertaining demo conversations."""
    chatbot = EmojiChatbot()

    demo_inputs = [
        "Hello! How are you?",
        "I'm hungry",
        "Let's play a game",
        "I love pizza",
        "I'm so tired",
        "What's the weather like?",
        "Do you like coding?",
        "I'm going to the beach",
        "Tell me a joke",
        "What do you think about cats?",
        "I won the lottery!",
        "My code has a bug",
        "Let's have a party",
        "I miss my friends",
        "What time is it?",
        "This is amazing!",
        "I'm so confused",
        "Swimming is fun",
        "Do you play football?",
        "Good morning!",
    ]

    print("\n" + "="*60)
    print("🤖 EMOJI CHATBOT - DEMO CONVERSATIONS 🤖")
    print("="*60 + "\n")

    for user_msg in demo_inputs:
        response = chatbot.process_input(user_msg)
        print(f"👤 User: {user_msg}")
        print(f"🤖 Bot:  {response}")
        print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        # Run demo mode
        demo_conversations()
    else:
        # Run interactive chat mode
        chatbot = EmojiChatbot()
        chatbot.chat()
