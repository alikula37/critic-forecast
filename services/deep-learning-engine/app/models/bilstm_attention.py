import torch
import torch.nn as nn
import torch.nn.functional as F

from .. import config


class AdditiveAttention(nn.Module):
    def __init__(self, dim):
        super().__init__()
        self.attn = nn.Linear(dim, dim)
        self.v = nn.Parameter(torch.randn(dim, 1) * 0.1)

    def forward(self, h):
        e = torch.tanh(self.attn(h))
        scores = torch.matmul(e, self.v).squeeze(-1)
        weights = F.softmax(scores, dim=1)
        context = torch.bmm(weights.unsqueeze(1), h).squeeze(1)
        return context, weights


class BiLSTMAttentionModel(nn.Module):
    def __init__(self, input_size, horizon, hidden_size=None, num_layers=None):
        super().__init__()
        hidden_size = hidden_size or config.HIDDEN_SIZE
        num_layers = num_layers or config.NUM_LAYERS
        self.lstm = nn.LSTM(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=config.DROPOUT if num_layers > 1 else 0.0,
        )
        dim = hidden_size * 2
        self.attention = AdditiveAttention(dim)
        self.gate = nn.Sequential(nn.Linear(dim, dim), nn.Sigmoid())
        self.heads = nn.ModuleList(
            [nn.Linear(dim, horizon) for _ in config.QUANTILES]
        )

    def forward(self, x):
        out, _ = self.lstm(x)
        context, weights = self.attention(out)
        gated = self.gate(context) * context + context
        return [head(gated) for head in self.heads], weights


class PinballLoss(nn.Module):
    def __init__(self, quantiles=None):
        super().__init__()
        self.quantiles = quantiles or config.QUANTILES

    def forward(self, preds, target):
        loss = 0.0
        for q, p in zip(self.quantiles, preds):
            err = target - p
            loss += torch.mean(torch.maximum(q * err, (q - 1) * err))
        return loss


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
