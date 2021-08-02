from typing import Dict, List, Union, Callable

import dgl
import torch

from torch import nn

from commons.mol_encoder import AtomEncoder, BondEncoder
from models.pna import PNALayer


class PNAGNNRandom(nn.Module):
    def __init__(self, random_vec_dim, n_model_confs, hidden_dim, aggregators: List[str], scalers: List[str],
                 residual: bool = True, pairwise_distances: bool = False, activation: Union[Callable, str] = "relu",
                 last_activation: Union[Callable, str] = "none", mid_batch_norm: bool = False,
                 last_batch_norm: bool = False, batch_norm_momentum=0.1, propagation_depth: int = 5,
                 dropout: float = 0.0, posttrans_layers: int = 1, pretrans_layers: int = 1, pretrain_mode=False, **kwargs):
        super(PNAGNNRandom, self).__init__()
        self.mp_layers = nn.ModuleList()
        self.random_vec_dim = random_vec_dim
        self.n_model_confs = n_model_confs
        self.pretrain_mode = pretrain_mode
        for _ in range(propagation_depth):
            self.mp_layers.append(
                PNALayer(in_dim=hidden_dim, out_dim=int(hidden_dim), in_dim_edges=hidden_dim, aggregators=aggregators,
                         scalers=scalers, pairwise_distances=pairwise_distances, residual=residual, dropout=dropout,
                         activation=activation, last_activation=last_activation, mid_batch_norm=mid_batch_norm,
                         last_batch_norm=last_batch_norm, avg_d={"log": 1.0}, posttrans_layers=posttrans_layers,
                         pretrans_layers=pretrans_layers, batch_norm_momentum=batch_norm_momentum
                         ),

            )
        self.atom_encoder = AtomEncoder(emb_dim=hidden_dim - self.random_vec_dim)
        self.bond_encoder = BondEncoder(emb_dim=hidden_dim - self.random_vec_dim)

    def forward(self, rand_x, rand_edge, dgl_graph: dgl.DGLGraph, **kwargs):
        dgl_graph.ndata['feat'] = self.atom_encoder(dgl_graph.ndata['feat'])
        dgl_graph.edata['feat'] = self.bond_encoder(dgl_graph.edata['feat'])
        if self.pretrain_mode:
            n_atoms, small_hidden_dim = dgl_graph.ndata['feat'].size()
            graph_confs = []
            for i in range(self.n_model_confs):
                graph_confs.append(dgl_graph.clone())
            graph_confs = dgl.batch(graph_confs)
            n_all_atoms = graph_confs.number_of_nodes()
            n_all_edges = graph_confs.number_of_edges()
            dgl_graph = graph_confs
            rand_x = rand_x.view(n_all_atoms, -1)
            rand_edge = rand_edge.view(n_all_edges, -1)
        dgl_graph.ndata['feat'] = torch.cat([dgl_graph.ndata['feat'], rand_x], dim=-1)
        dgl_graph.edata['feat'] = torch.cat([dgl_graph.edata['feat'], rand_edge], dim=-1)

        for mp_layer in self.mp_layers:
            mp_layer(dgl_graph)

        if self.pretrain_mode:
            feat = dgl_graph.ndata['feat'].view(n_atoms, -1, small_hidden_dim + self.random_vec_dim)
        else:
            feat = dgl_graph.ndata['feat']
        return feat, None