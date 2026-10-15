"""The evaluation corpus: 4 synthetic research papers written for measuring this project.

The real papers cannot be put in the repo (they belong to their authors), so these are written
to look like real papers to the PDF reader: a running header on every page, page numbers, an
arXiv-style rotated stamp on page 1, a results table drawn with lines, and a reference list.
Every fact sits on one known page, so questions.json can say which page holds each answer.

Usage: python -m evaluation.corpus [output_dir]   (default: .cache/eval_corpus)
"""

import sys
from pathlib import Path

from tests.pdf_writer import make_pdf

NOTE = "Synthetic text written to evaluate a question answering system. It is not a real research paper."
HEADER = "Proceedings of the Workshop on Game AI Testing 2026"

PAPERS: dict[str, dict] = {
    "evo_level_generation.pdf": {
        "watermark": "arXiv:2603.04117v1 [cs.AI] 6 Mar 2026",
        "pages": [
            "Evolving Playable Platformer Levels with a Two-Objective Genetic Algorithm\n\n"
            "R. Mehta and L. Park, Department of Computer Science. " + NOTE + "\n\n"
            "Abstract. Designing levels for a 2D platform game by hand takes designers several weeks for every new "
            "world. We present a genetic algorithm that generates complete platformer levels and optimises two "
            "objectives at the same time: playability and novelty. A level is playable when an automated agent can "
            "reach the goal, and it is novel when it differs from the levels that were generated before. We tested "
            "the method on three games called Tunnel Run, Sky Hop and Crate Quest. On average 92.5 percent of the "
            "generated levels were playable, compared with 61 percent of levels made by random generation.\n\n"
            "Introduction. Procedural content generation lets a computer create game content such as maps, items "
            "and levels. Earlier generators often produced levels that look interesting but cannot be finished, "
            "because a gap is too wide or an enemy blocks the only path. Our generator checks every level with a "
            "planning agent while it searches, so unplayable levels are removed early.",

            "Level representation. A level is a grid of 16 rows and 120 columns. Every cell holds one tile type: "
            "empty space, ground, gap, enemy, coin or spring. Instead of evolving single tiles, the genome is a "
            "sequence of 30 segments, and each segment is 4 columns wide. Every segment is chosen from a library of "
            "48 hand-made segments that were drawn by a level designer, so small parts of a level always look "
            "sensible.\n\n"
            "Genetic operators. Mutation replaces one segment with a random segment from the library, with a "
            "probability of 0.05 for every position in the genome. Crossover is one-point crossover: two parent "
            "levels are cut at the same random position and the parts are swapped. Because both parents use the "
            "same segment boundaries, crossover never breaks a segment in the middle. The first population is filled "
            "with random sequences of segments.",

            "Fitness function. Playability is tested by an A* search agent that knows the movement rules of the "
            "game, such as jump height and running speed. The agent tries to find a path from the start to the "
            "goal; the playability score is the fraction of the level that the agent can cross before it fails, so "
            "a fully playable level scores 1. Novelty is the average Hamming distance between the new level and the "
            "10 nearest levels in an archive of earlier levels. The fitness of a level is 0.6 times playability "
            "plus 0.4 times novelty.\n\n"
            "Search settings. We used a population of 64 levels and ran the search for 200 generations. Parents are "
            "picked with tournament selection with a tournament size of 3. The best 2 levels of every generation are "
            "copied unchanged into the next generation (elitism). One full run took about 35 minutes on the CPU of "
            "a normal laptop.",

            {
                "text": "Results. Table 1 shows the share of playable levels for each game, and the average novelty "
                        "of the generated levels. The genetic algorithm produced far more playable levels than "
                        "random generation in all three games. Crate Quest had the most novel levels, because its "
                        "segment library contains many different crate arrangements. Sky Hop was the hardest game "
                        "for the generator, because its springs make many jumps depend on exact timing.\n\n"
                        "Table 1: Playable levels in percent and average novelty for each game.",
                "table": [
                    ["Game", "Playable (GA)", "Playable (random)", "Novelty"],
                    ["Tunnel Run", "94.0", "58.0", "0.41"],
                    ["Sky Hop", "91.5", "63.5", "0.37"],
                    ["Crate Quest", "92.0", "61.5", "0.44"],
                ],
            },

            "User study. We asked 24 players to play 6 levels each: two levels made by the genetic algorithm, two "
            "made by a human designer and two made by random generation, in a random order. After every level the "
            "players rated how much fun it was on a 7-point Likert scale. Levels from the genetic algorithm got an "
            "average fun rating of 5.3, designer levels got 5.6 and random levels got 3.1. Several players said that "
            "the generated levels felt fair but sometimes repeated the same jump pattern.\n\n"
            "Limitations and future work. The A* agent only tells whether a level can be finished, not how hard it "
            "is for a human, so a level can be playable but frustrating. In future work we want to replace the A* "
            "agent with a player model learned from recorded play sessions, so the generator can aim for a chosen "
            "difficulty.",

            "References\n\n"
            "[1] J. Togelius and G. Yannakakis. Search-based procedural content generation: a taxonomy and survey. "
            "Transactions on Computational Intelligence and AI in Games, 2011.\n\n"
            "[2] N. Shaker, J. Togelius and M. Nelson. Procedural Content Generation in Games. Springer, 2016.\n\n"
            "[3] J. Lehman and K. Stanley. Abandoning objectives: evolution through the search for novelty "
            "alone. Evolutionary Computation, 2011.\n\n"
            "[4] A. Summerville et al. Procedural content generation via machine learning. Transactions on "
            "Games, 2018.\n\n"
            "[5] S. Snodgrass and S. Ontanon. Learning to generate video game maps using Markov models. Transactions "
            "on Computational Intelligence and AI in Games, 2017.",
        ],
    },
    "crash_hunter_rl.pdf": {
        "watermark": "arXiv:2604.11820v2 [cs.SE] 19 Apr 2026",
        "pages": [
            "CrashHunter: Finding Crashes in Mobile Games with Curiosity-Driven Reinforcement Learning\n\n"
            "A. Rossi, K. Tanaka and M. Okafor. " + NOTE + "\n\n"
            "Abstract. Crashes are the most harmful bugs in mobile games, because a crash ends the session and many "
            "players uninstall a game after it crashes twice. We present CrashHunter, a deep Q-network agent with a "
            "curiosity bonus that plays Android games on its own and looks for crashes. In 48 hours of testing on 12 "
            "test games, CrashHunter found 37 unique crashes. The Monkey tool, which sends random taps, found only 9 "
            "crashes in the same time.\n\n"
            "Introduction. Game studios test mobile games with scripted tests and with human testers, but scripts "
            "break whenever the user interface changes, and human testing is expensive. A reinforcement learning "
            "agent does not need scripts: it learns from the screen which actions lead to new parts of the game.",

            "Test environment. Every game runs in an Android emulator with API level 33. The agent sees the screen "
            "as an 84 by 84 pixel grayscale image, captured after every action. The action space has 69 actions: a "
            "tap on one of 64 cells of an 8 by 8 grid laid over the screen, a swipe in one of 4 directions, and the "
            "Android back button.\n\n"
            "Reward function. The agent gets a reward of +10 when it reaches a screen it has not seen before. Two "
            "screens count as the same when their perceptual hashes are equal, so small animations do not create "
            "new screens. A crash gives a reward of +100, and the game is restarted afterwards. Every step that does "
            "not change the screen costs -1, which teaches the agent to avoid tapping on empty areas.",

            "Curiosity module. Many crashes hide deep in menus that a normal agent rarely reaches. To push the agent "
            "towards unfamiliar states we add Random Network Distillation (RND): a fixed random network and a "
            "predictor network both read the screen, and the prediction error is used as an intrinsic reward. The "
            "intrinsic reward is multiplied by a scale of 0.5 before it is added to the game reward.\n\n"
            "Training settings. The Q-network uses a replay buffer with 100,000 transitions and the Adam optimiser "
            "with a learning rate of 0.0001. Exploration follows an epsilon-greedy policy, where epsilon decays "
            "from 1.0 to 0.05 over the first 50,000 steps. The target network is updated every 2,000 steps.",

            {
                "text": "Results. Table 1 compares CrashHunter with three other approaches after 48 hours of testing "
                        "on the same 12 games. CrashHunter found the most unique crashes and covered the most "
                        "screens. Removing the curiosity module lowered the number of crashes from 37 to 21, which "
                        "shows that curiosity matters for deep menus. Of the 37 crashes found by CrashHunter, 15 "
                        "were null pointer exceptions, 9 were application not responding (ANR) errors, 8 were out "
                        "of memory errors and 5 were native crashes in the game engine.\n\n"
                        "Table 1: Unique crashes and screens covered after 48 hours.",
                "table": [
                    ["Tool", "Unique crashes", "Screens covered"],
                    ["CrashHunter", "37", "412"],
                    ["DQN without curiosity", "21", "301"],
                    ["Monkey", "9", "198"],
                    ["Random agent", "6", "175"],
                ],
            },

            "Reproducing crashes. A crash report is only useful when developers can reproduce it. CrashHunter saves "
            "the full action sequence that led to every crash, and a replay tool sends the same actions to a fresh "
            "emulator. Replaying reproduced 33 of the 37 crashes, which is 89 percent. The other 4 crashes depended "
            "on timing or on network delays.\n\n"
            "Limitations. CrashHunter cannot type text, so games that start with a text field, for example a name "
            "entry, block it. Games that need an online login were left out of the study. We ran 4 emulators in "
            "parallel on one machine with 32 GB of memory; more emulators made the screens lag and changed the "
            "results.",

            "References\n\n"
            "[1] V. Mnih et al. Human-level control through deep reinforcement learning. Nature, 2015.\n\n"
            "[2] Y. Burda, H. Edwards, A. Storkey and O. Klimov. Exploration by random network distillation. "
            "International Conference on Learning Representations, 2019.\n\n"
            "[3] D. Pathak et al. Curiosity-driven exploration by self-supervised prediction. International "
            "Conference on Machine Learning, 2017.\n\n"
            "[4] Y. Zheng et al. Wuji: automatic online combat game testing using evolutionary deep reinforcement "
            "learning. Automated Software Engineering, 2019.\n\n"
            "[5] Android Developers. UI/Application Exerciser Monkey. Developer documentation, 2024.",
        ],
    },
    "churn_prediction_telemetry.pdf": {
        "watermark": "arXiv:2605.00731v1 [cs.LG] 2 May 2026",
        "pages": [
            "Predicting Player Churn from Early Gameplay Telemetry\n\n"
            "S. Iyer and D. Novak. " + NOTE + "\n\n"
            "Abstract. Most players of free mobile games stop playing within the first weeks. We predict whether a "
            "player will churn, meaning stop playing, using only telemetry from the first 3 days after install. The "
            "data set contains 1.2 million play sessions from 85,000 players of the mobile puzzle game Puzzle "
            "Garden. A gradient boosted tree model (LightGBM) reached an AUC of 0.87, while logistic regression "
            "reached 0.79. The most useful signals were the days since the last session and repeated failures on "
            "one level.\n\n"
            "Introduction. If a studio knows early which players are likely to leave, it can change the game for "
            "them, for example by offering help on a hard level. Earlier studies used weeks of data; we show that "
            "three days are enough for a useful prediction.",

            "Churn definition. A player has churned when there is no play session between day 15 and day 28 after "
            "install. With this definition the churn rate in the data set is 41 percent.\n\n"
            "Features. From the first 3 days of telemetry we compute 23 features in 4 groups. Engagement features "
            "describe how much a player plays, such as sessions per day and the average session length. Progress "
            "features describe how far a player gets, such as the number of levels completed and the number of "
            "failed attempts on each level. Social features count friends invited and gifts sent. Monetization "
            "features count purchases and the number of rewarded ads watched.",

            "Model. The main model is LightGBM with 400 trees, a learning rate of 0.05 and a maximum tree depth of "
            "6. Because churned and active players are not equally common, we use class weights during training. "
            "All results come from 5-fold cross validation, where every player appears in exactly one test fold.\n\n"
            "Baselines. We compare LightGBM with logistic regression, which is easy to explain, and with a random "
            "forest of 300 trees. All models use the same 23 features. Missing values, for example the session "
            "length of a player with no session on day 3, are filled with zero and an extra flag feature.",

            {
                "text": "Results. Table 1 shows that LightGBM is the best model on all three measures. Precision at "
                        "10 percent means: among the 10 percent of players with the highest predicted churn risk, "
                        "how many really churned. To explain the model we computed SHAP values. The three most "
                        "important features were the days since the last session, the number of failed attempts on "
                        "level 12, and the average session length.\n\n"
                        "Table 1: Churn prediction results with 5-fold cross validation.",
                "table": [
                    ["Model", "AUC", "F1", "Precision at 10%"],
                    ["LightGBM", "0.87", "0.74", "0.81"],
                    ["Random forest", "0.84", "0.71", "0.77"],
                    ["Logistic regression", "0.79", "0.66", "0.69"],
                ],
            },

            "Discussion. The high importance of failed attempts on level 12 pointed to a difficulty spike. The "
            "developers of Puzzle Garden made level 12 easier for half of the new players in an A/B test. In that "
            "group the 14-day retention rose by 3.8 percentage points, so the model also helped to find a design "
            "problem.\n\n"
            "Ethics and limitations. The telemetry was anonymised by the studio before we received it, and it "
            "contains no names, e-mail addresses or locations. All data comes from one puzzle game, so the model "
            "and its most important features may be different for other genres such as shooters or racing games.",

            "References\n\n"
            "[1] G. Ke et al. LightGBM: a highly efficient gradient boosting decision tree. Advances in Neural "
            "Information Processing Systems, 2017.\n\n"
            "[2] S. Lundberg and S. Lee. A unified approach to interpreting model predictions. Advances in Neural "
            "Information Processing Systems, 2017.\n\n"
            "[3] J. Runge et al. Churn prediction for high-value players in casual social games. Conference on "
            "Computational Intelligence and Games, 2014.\n\n"
            "[4] F. Hadiji et al. Predicting player churn in the wild. Conference on Computational Intelligence and "
            "Games, 2014.\n\n"
            "[5] A. Drachen et al. Game Analytics: Maximizing the Value of Player Data. Springer, 2013.",
        ],
    },
    "glitch_autoencoder.pdf": {
        "watermark": "arXiv:2606.02295v1 [cs.CV] 3 Jun 2026",
        "pages": [
            "Detecting Visual Glitches in Racing Game Frames with a Convolutional Autoencoder\n\n"
            "M. Laurent and P. Chen. " + NOTE + "\n\n"
            "Abstract. Visual glitches such as missing textures or flickering surfaces are easy for people to see "
            "but hard to find automatically. We train a convolutional autoencoder only on normal frames of the "
            "racing game Neon Drift. A frame is marked as glitched when the autoencoder cannot rebuild it well, "
            "that is when its reconstruction error is above a threshold. The data set has 24,000 frames. On the "
            "test set the method reaches an F1 score of 0.81 without ever seeing a labelled glitch during "
            "training.\n\n"
            "Introduction. Supervised glitch detectors need many labelled examples of every glitch type, and new "
            "glitch types appear with every engine update. An autoencoder learns what normal frames look like, so "
            "it can flag any unusual frame.",

            "Data set. We recorded 20,000 normal frames while a bot drove laps on 6 tracks; these frames are used "
            "for training. The test set has 4,000 frames, of which 2,000 contain a glitch.\n\n"
            "Glitch types. We injected five glitch types through modified shaders. A missing texture shows a "
            "magenta and black checkerboard instead of the surface. Stretched polygons pull a vertex far away, so a "
            "thin spike crosses the screen. Z-fighting makes two surfaces flicker because they lie at the same "
            "depth. Wrong lighting renders a car completely black. Floating objects are small props such as cones "
            "that hover above the road.",

            "Model. Frames are scaled down to 128 by 128 pixels with 3 colour channels. The encoder has 4 "
            "convolution layers with 32, 64, 128 and 256 filters, followed by a latent vector of size 512. The "
            "decoder mirrors the encoder with transposed convolutions.\n\n"
            "Training. The autoencoder was trained for 60 epochs with the Adam optimiser, a learning rate of "
            "0.001, a batch size of 64 and the mean squared error as the loss. Training took 3 hours on one "
            "RTX 3060 graphics card.",

            {
                "text": "Threshold and results. The threshold is the 99th percentile of the reconstruction errors on "
                        "a validation set of normal frames, which gave a value of 0.035. Table 1 lists precision "
                        "and recall for every glitch type. Missing textures and wrong lighting change many pixels "
                        "and were found reliably. Z-fighting and floating objects were found much less often.\n\n"
                        "Table 1: Precision and recall for each glitch type.",
                "table": [
                    ["Glitch type", "Precision", "Recall"],
                    ["Missing texture", "0.95", "0.93"],
                    ["Stretched polygons", "0.88", "0.84"],
                    ["Z-fighting", "0.62", "0.55"],
                    ["Wrong lighting", "0.90", "0.86"],
                    ["Floating objects", "0.58", "0.49"],
                ],
            },

            "Discussion. Floating objects are hard to detect because a hovering cone changes only a few hundred "
            "pixels, which barely raises the reconstruction error of the whole frame. Z-fighting is a problem over "
            "time, so a single frame often looks normal. A map of the per-pixel error shows where the glitch is, "
            "which helps testers to check a report quickly.\n\n"
            "Comparison. A supervised ResNet-18 classifier trained on labelled glitches reached an F1 score of "
            "0.89, but it needed 8,000 labelled glitch frames. In future work we will add temporal models that "
            "look at several frames at once, to catch flickering glitches.",

            "References\n\n"
            "[1] D. Kingma and J. Ba. Adam: a method for stochastic optimization. International Conference on "
            "Learning Representations, 2015.\n\n"
            "[2] K. He et al. Deep residual learning for image recognition. Conference on Computer Vision and "
            "Pattern Recognition, 2016.\n\n"
            "[3] C. Ling et al. Using deep convolutional neural networks to detect rendered glitches in video "
            "games. Conference on Artificial Intelligence and Interactive Digital Entertainment, 2020.\n\n"
            "[4] B. Wilkins and K. Stathis. World of Bugs: a platform for automated bug detection in 3D video "
            "games. Conference on Games, 2022.\n\n"
            "[5] J. An and S. Cho. Variational autoencoder based anomaly detection using reconstruction "
            "probability. Special Lecture on IE, 2015.",
        ],
    },
}


def build_corpus(output_dir: str | Path) -> list[Path]:
    """Write the 4 papers as PDFs into output_dir and return their paths."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, paper in PAPERS.items():
        path = output_dir / name
        make_pdf(path, paper["pages"], header=HEADER, page_numbers=True, watermark=paper["watermark"])
        paths.append(path)
    return paths


if __name__ == "__main__":
    for path in build_corpus(sys.argv[1] if len(sys.argv) > 1 else ".cache/eval_corpus"):
        print(f"Created {path}")
