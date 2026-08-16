import os

import torch

EPOCHS = int(os.getenv("DLE_EPOCHS", "80"))
WF_EPOCHS = int(os.getenv("DLE_WALKFORWARD_EPOCHS", "25"))
BATCH_SIZE = int(os.getenv("DLE_BATCH_SIZE", "32"))
SEQUENCE_LEN = int(os.getenv("DLE_SEQUENCE_LEN", "60"))
HIDDEN_SIZE = 64
NUM_LAYERS = 2
DROPOUT = 0.25
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4
PATIENCE = 12
QUANTILES = [0.10, 0.50, 0.90]
N_FOLDS = 3
WF_STRIDE = 5
WF_TREE_ESTIMATORS = 60
XGB_ESTIMATORS = 120
LGB_ESTIMATORS = 90
DEVICE = "cpu"
SEED = 42

import random

random.seed(SEED)
torch.manual_seed(SEED)
import numpy as np

np.random.seed(SEED)
