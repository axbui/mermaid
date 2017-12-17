from __future__ import print_function

import numpy as np


def get_multi_metric(pred, gt, eval_label_list = None, rm_bg=False):
    """
    implemented iou, dice, recall, precision metrics for each label of each instance in batch

    :param pred:  predicted(warpped) label map Bx....
    :param gt: ground truth label map  Bx....
    :param eval_label_list: manual selected label need to be evaluate
    :param rm_bg: remove the background label, assume the background label is the first label of label_list when using auto detection
    :return: Bx num_label_evaluated    dictonary, each item represents one metric method, a matrix for metric results of each label of each instance
    """
    pred = pred.cpu().data.numpy()
    gt = gt.cpu().data.numpy()
    label_list = np.unique(gt).tolist()
    if rm_bg:
        label_list = label_list[1:]
    if eval_label_list is not None:
        for label in eval_label_list:
            assert label in label_list, "label {} is not in label_list".format(label)
        label_list = eval_label_list
    num_label = len(label_list)
    num_batch = pred.shape[0]
    dice_multi = np.zeros([num_batch, num_label])
    iou_multi = np.zeros([num_batch, num_label])
    precision_multi = np.zeros([num_batch, num_label])
    recall_multi = np.zeros([num_batch, num_label])
    for l in range(num_label):
        label_pred = (pred == label_list[l]).astype(np.int32)
        label_gt = (gt == label_list[l]).astype(np.int32)
        for b in range(num_batch):
            metric_res = cal_metric(label_pred[b].reshape(-1),  label_gt[b].reshape(-1))
            dice_multi[b][l] =metric_res['dice']
            iou_multi[b][l] = metric_res['dice']
            precision_multi[b][l] = metric_res['dice']
            recall_multi[b][l] = metric_res['dice']

    multi_metric_res = {'iou': iou_multi, 'dice': dice_multi, 'recall': recall_multi, 'precision': precision_multi}

    return multi_metric_res




def cal_metric(label_pred, label_gt):
    eps = 1e-11
    iou = -1
    recall = -1
    precision = -1
    dice = -1
    gt_loc = set(np.where(label_gt == 1)[0])
    pred_loc = set(np.where(label_pred == 1)[0])
    total_len = len(label_gt)
    # iou
    intersection = set.intersection(gt_loc, pred_loc)
    union = set.union(gt_loc, pred_loc)
    # recall
    len_intersection = len(intersection)
    tp = float(len_intersection)
    tn = float(total_len - len(union))
    fn = float(len(gt_loc) - len_intersection)
    fp = float(len(pred_loc) - len_intersection)

    if len(gt_loc) != 0:
        iou = tp / (float(len(union))+eps)
        recall = tp/(tp+fn+eps)
        precision = tp/(tp+fp+eps)
        dice = 2*tp/(2*tp+fn+fp+eps)

    res={'iou': iou, 'dice': dice, 'recall': recall, 'precision': precision}

    return res

