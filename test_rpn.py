#!/usr/bin/python3
# Copyright 2017, Mengxiao Lin <linmx0130@gmail.com>

import argparse
from faster_rcnn.config import cfg
from VOCDataset import VOCDataset
from faster_rcnn.rpn import RPNBlock
import torch
from faster_rcnn.utils import imagenetNormalize, img_resize, bbox_inverse_transform, select_class_generator
from faster_rcnn.anchor_generator import generate_anchors, map_anchors
from faster_rcnn.vis_tool import show_anchors
from faster_rcnn.nms import nms




plt.ion()   # interactive mode



def parse_args():
    parser = argparse.ArgumentParser(description="Test RPN")
    parser.add_argument('model_file', metavar='model_file', type=str)
    parser.add_argument('--show_top_n', metavar='show_top_n', type=int, default=4)
    return parser.parse_args()


def test_transformation(data, label):
    data = imagenetNormalize(data)
    return data, label

test_dataset = VOCDataset(annotation_dir=cfg.test_annotation_dir,
                           img_dir=cfg.test_img_dir,
                           dataset_index=cfg.test_dataset_index,
                           transform=test_transformation,
                           resize_func=img_resize)

test_datait = mx.gluon.data.DataLoader(test_dataset, batch_size=1, shuffle=False)
ctx = mx.gpu(0)
net = RPNBlock(len(cfg.anchor_ratios) * len(cfg.anchor_scales))
net.init_params(ctx)
args = parse_args()
print("Load model: {}".format(args.model_file))
net.collect_params().load(args.model_file, ctx)

for it, (data, label) in enumerate(test_datait):
    data = data.as_in_context(ctx)
    _n, _c, h, w = data.shape
    label = label.as_in_context(ctx)
    rpn_cls, rpn_reg, f = net(data)
    f_height = f.shape[2]
    f_width = f.shape[3]
    rpn_cls = rpn_cls.reshape((1, -1, 2, f_height, f_width))
    anchors_count = rpn_cls.shape[1]

    ref_anchors = generate_anchors(base_size=16, ratios=cfg.anchor_ratios, scales=cfg.anchor_scales)
    anchors = map_anchors(ref_anchors, rpn_reg.shape, h, w, ctx)
    anchors = anchors.reshape((1, -1, 4, f_height, f_width))
    anchors = mx.nd.transpose(anchors, (0, 3, 4, 1, 2))
    rpn_anchor_scores = mx.nd.softmax(mx.nd.transpose(rpn_cls, (0, 3, 4, 1, 2)), axis=4)[:,:,:,:,1]
    
    rpn_reg = mx.nd.transpose(rpn_reg.reshape((1, -1, 4, f_height, f_width)), (0, 3, 4, 1, 2))
    rpn_bbox_pred = bbox_inverse_transform(anchors.reshape((-1, 4)), rpn_reg.reshape((-1, 4))).reshape((1, f_height, f_width, anchors_count, 4))
    rpn_bbox_pred = rpn_bbox_pred.asnumpy().reshape((-1, 4))
    rpn_anchor_scores = rpn_anchor_scores.asnumpy().reshape((-1, ))
    rpn_anchor_scores, rpn_bbox_pred = nms(rpn_anchor_scores, rpn_bbox_pred, cfg.nms_thresh)
    rpn_anchor_scores = mx.nd.array(rpn_anchor_scores.reshape((1, -1)))
    rpn_bbox_pred = mx.nd.array(rpn_bbox_pred.reshape((1, -1, 4)))
    show_anchors(data, label, rpn_bbox_pred, mx.nd.ones(rpn_anchor_scores.shape), count=args.show_top_n)
