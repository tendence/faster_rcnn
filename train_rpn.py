#!/usr/bin/python3
# Copyright 2017, Mengxiao Lin <linmx0130@gmail.com>

from faster_rcnn.config import cfg
from VOCDataset import VOCDataset
from faster_rcnn.rpn import RPNBlock
import mxnet as mx
from faster_rcnn.utils import random_flip, imagenetNormalize, img_resize, random_square_crop, select_class_generator, bbox_inverse_transform, softmax_celoss_with_ignore
from faster_rcnn.rpn_gt_opr import rpn_gt_opr
from faster_rcnn.vis_tool import show_anchors

def train_transformation(data, label):
    data, label = random_flip(data, label)
    data = imagenetNormalize(data)
    return data, label

train_dataset = VOCDataset(annotation_dir=cfg.annotation_dir,
                           img_dir=cfg.img_dir,
                           dataset_index=cfg.dataset_index,
                           transform=train_transformation,
                           resize_func=img_resize)

train_datait = mx.gluon.data.DataLoader(train_dataset, batch_size=1, shuffle=True)
ctx = mx.gpu(0)
net = RPNBlock(len(cfg.anchor_ratios) * len(cfg.anchor_scales))
net.init_params(ctx)
trainer = mx.gluon.trainer.Trainer(net.collect_params(), 
                                    'sgd', 
                                    {'learning_rate': 0.001,
                                     'wd': 0.0005,
                                     'momentum': 0.9})

anchors_count = len(cfg.anchor_ratios) * len(cfg.anchor_scales)
for epoch in range(20):
    for it, (data, label) in enumerate(train_datait):
        data = data.as_in_context(ctx)
        _n, _c, h, w = data.shape
        label = label.as_in_context(ctx).reshape((1, -1, 5))
        with mx.autograd.record():
            rpn_cls, rpn_reg, f = net(data)
            f_height = f.shape[2]
            f_width = f.shape[3]
            rpn_cls_gt, rpn_reg_gt = rpn_gt_opr(rpn_reg.shape, label, ctx, h, w)
            # Reshape and transpose to the shape of gt
            rpn_cls = rpn_cls.reshape((1, -1, 2, f_height, f_width))
            rpn_cls = mx.nd.transpose(rpn_cls, (0, 1, 3, 4, 2))
            rpn_reg = mx.nd.transpose(rpn_reg.reshape((1, -1, 4, f_height, f_width)), (0, 1, 3, 4, 2))
            mask = (rpn_cls_gt==1).reshape((1, anchors_count, f_height, f_width, 1)).broadcast_to((1, anchors_count, f_height, f_width, 4))
            loss_reg = mx.nd.sum(mx.nd.smooth_l1((rpn_reg - rpn_reg_gt) * mask, 3.0)) / mx.nd.sum(mask)
            loss_cls = softmax_celoss_with_ignore(rpn_cls.reshape((-1, 2)), rpn_cls_gt.reshape((-1, )), -1)
            loss = loss_cls + loss_reg 
        loss.backward()
        print("Epoch {} Iter {}: loss={:.4}, loss_cls={:.4}, loss_reg={:.4}".format(
                epoch,it, loss.asscalar(), loss_cls.asscalar(), loss_reg.asscalar()))
        trainer.step(data.shape[0])
    net.collect_params().save(cfg.model_path_pattern.format(epoch)) 
