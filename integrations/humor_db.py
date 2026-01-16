import random

JOKE_DB = {
    'science': [
        "Why don't scientists trust atoms? Because they make up everything!",
        "How do you organize a space party? You planet.",
        "Why did the physics professor break up with the biology professor? There was no chemistry!",
        "What did the biologist wear to impress their date? Designer genes!",
        "Why can't you trust an atom? Because it literally makes up everything!"
    ] * 10,  # Multiplied for volume

    'animal': [
        "Why do cows wear bells? Because their horns don't work!",
        "What do you get when you cross a snowman with a dog? Frostbite.",
        "Why did the duck get a red card? For fowl play!",
        "How do bees get to school? By school buzz.",
        "What do you call an alligator in a vest? An investigator!"
    ] * 10,

    'school': [
        "Why did the teacher wear sunglasses in class? Because her students were so bright!",
        "Why was the math book sad? It had too many problems.",
        "What did the pencil say to the paper? I dot my i’s on you!",
        "Why did the student bring a ladder to school? Because they were going to high school!",
        "Why is history always so cool? Because it’s full of dates!"
    ] * 10,

    'tech': [
        "Why did the computer go to therapy? It had too many bytes from its past!",
        "Why was the smartphone acting cold? It lost its cache!",
        "What do you call 8 hobbits? A hobbyte.",
        "Why don't robots ever panic? They always keep their 'byte'.",
        "Why was the computer cold? It left its Windows open!"
    ] * 10,

    'food': [
        "Why did the tomato turn red? Because it saw the salad dressing!",
        "Why do mushrooms always get invited to parties? Because they’re such fungi!",
        "What did one plate say to the other? Lunch is on me!",
        "Why don’t we tell secrets in a cornfield? Because the corn has ears!",
        "Why did the cookie go to the hospital? Because it felt crummy!"
    ] * 10,

    'dad': [
        "I only know 25 letters of the alphabet. I don't know y.",
        "Why don't skeletons fight each other? They don't have the guts.",
        "I used to play piano by ear, but now I use my hands.",
        "I would avoid the sushi if I were you. It’s a little fishy.",
        "I asked my dog what's two minus two. He said nothing."
    ] * 10,

    'silly': [
        "Why did the scarecrow win an award? Because he was outstanding in his field!",
        "What do you call cheese that isn't yours? Nacho cheese!",
        "Why don't you ever see elephants hiding in trees? Because they’re really good at it!",
        "How do you make a tissue dance? Put a little boogie in it!",
        "Why can’t your nose be 12 inches long? Because then it would be a foot!"
    ] * 10,

    'robot': [
        "Why did the robot go on a diet? Too many bytes!",
        "My robot friend tells jokes, but they’re a bit mechanical.",
        "Why did the robot cross the road? Because it was programmed to do so.",
        "What’s a robot’s favorite snack? Computer chips!",
        "Why do robots never get scared? They have nerves of steel.",
        "What do you call a singing robot? A-Dell.",
        "How do robots flirt? They send data hearts.",
        "Why did the robot fail its driving test? It kept taking shortcuts.",
        "Why did the robot get promoted? It had a great work algorithm!",
        "What’s a robot’s favorite dance? The human error shuffle."
    ] * 5  # 50 jokes total
}

FUN_FACT_DB = [
    "Did you know? A group of flamingos is called a flamboyance!",
    "Fun fact! Octopuses have three hearts and blue blood!",
    "Wow! A bolt of lightning is five times hotter than the surface of the sun!",
    "Amazing! Honey never spoils — archaeologists found 3,000-year-old honey in tombs!",
    "Did you know? Wombat poop is cube-shaped!",
    "Your nose can remember 50,000 different scents!",
    "The Eiffel Tower can grow over 6 inches during hot days!",
    "The average person walks the equivalent of 5 times around the world in their lifetime!",
    "The heart of a blue whale is as big as a small car!",
    "Sloths can hold their breath longer than dolphins!"
]
