# -*- coding: utf-8 -*-
# @Time    : 2018/8/23 22:20
# @Author  : zhoujun

import os
import pickle
import shutil
import pathlib
from pprint import pformat
import mxnet as mx
from mxnet import nd, gluon
import traceback

from utils import setup_logger, try_gpu


class TRAIN_STATE:
    def __init__(self):
        self.epoch = 0
        self.lr = 0


class BaseTrainer:
    def __init__(self, config, model, criterion, ctx):
        config['trainer']['output_dir'] = os.path.join(str(pathlib.Path(os.path.abspath(__name__)).parent),
                                                       config['trainer']['output_dir'])
        save_dir = os.path.join(config['trainer']['output_dir'], config['name'])
        self.checkpoint_dir = os.path.join(config['trainer']['output_dir'], config['name'], 'checkpoint')

        if config['trainer']['resume']['restart_training']:
            shutil.rmtree(save_dir, ignore_errors=True)
        if not os.path.exists(self.checkpoint_dir):
            os.makedirs(self.checkpoint_dir)

        self.global_step = 0
        self.start_epoch = 1
        self.config = config

        self.model = model
        self.criterion = criterion
        # logger and tensorboard
        self.tensorboard_enable = self.config['trainer']['tensorboard']
        self.epochs = self.config['trainer']['epochs']
        self.display_interval = self.config['trainer']['display_interval']
        if self.tensorboard_enable:
            from mxboard import SummaryWriter
            self.writer = SummaryWriter(save_dir)

        self.logger = setup_logger(os.path.join(save_dir, 'train_log'))
        self.logger.info(pformat(self.config))

        # device set
        self.ctx = ctx
        mx.random.seed(2)  # 为CPU设置随机种子
        mx.random.seed(2, ctx=self.ctx)

        self.logger.info('train with mxnet: {} and device: {}'.format(mx.__version__, self.ctx))
        self.metrics = {'val_acc': 0, 'train_loss': float('inf'), 'best_model': ''}

        schedule = self._initialize('lr_scheduler', mx.lr_scheduler)
        optimizer = self._initialize('optimizer', mx.optimizer, lr_scheduler=schedule)
        self.trainer = gluon.Trainer(self.model.collect_params(), optimizer=optimizer)

        if self.config['trainer']['resume']['checkpoint'] != '' and not self.config['trainer']['resume'][
            'restart_training']:
            self._resume_checkpoint(self.config['trainer']['resume']['checkpoint'])
            self.config['lr_scheduler']['args']['last_epoch'] = self.start_epoch

        # todo 单机多卡

        if self.tensorboard_enable:
            try:
                # add graph
                dummy_input = nd.zeros((1, self.config['data_loader']['args']['dataset']['img_channel'],
                                        self.config['data_loader']['args']['dataset']['img_h'],
                                        self.config['data_loader']['args']['dataset']['img_w']), ctx=self.ctx)
                self.model(dummy_input)
                self.writer.add_graph(model)
            except:
                self.logger.error(traceback.format_exc())
                self.logger.warn('add graph to tensorboard failed')

    def train(self):
        """
        Full training logic
        """
        for epoch in range(self.start_epoch, self.epochs + 1):
            try:
                self.epoch_result = self._train_epoch(epoch)
                self._on_epoch_finish()
            except:
                self.logger.error(traceback.format_exc())
        if self.tensorboard_enable:
            self.writer.close()
        self._on_train_finish()

    def _train_epoch(self, epoch):
        """
        Training logic for an epoch

        :param epoch: Current epoch number
        """
        raise NotImplementedError

    def _eval(self):
        """
        eval logic for an epoch

        :param epoch: Current epoch number
        """
        raise NotImplementedError

    def _on_epoch_finish(self):
        raise NotImplementedError

    def _on_train_finish(self):
        raise NotImplementedError

    def _save_checkpoint(self, epoch, file_name, save_best=False):
        """
        保存模型和检查点信息，会保存模型权重，trainer状态，其他的信息
        :param epoch: 当前epoch
        :param file_name: 文件名
        :param save_best: 是否是最优模型
        :return:
        """

        # 保存权重
        params_filename = os.path.join(self.checkpoint_dir, file_name)
        self.model.save_parameters(params_filename)
        # 保存trainer状态
        trainer_filename = params_filename.replace('.params', '.train_states')
        self.trainer.save_states(trainer_filename)
        # 其他信息
        state = {
            'epoch': epoch,
            'global_step': self.global_step,
            'config': self.config,
            'metrics': self.metrics
        }
        other_filename = params_filename.replace('.params', '.info')
        pickle.dump(state, open(other_filename, 'wb'))
        if save_best:
            shutil.copy(params_filename, os.path.join(self.checkpoint_dir, 'model_best.params'))
            shutil.copy(trainer_filename, os.path.join(self.checkpoint_dir, 'model_best.train_states'))
            shutil.copy(other_filename, os.path.join(self.checkpoint_dir, 'model_best.info'))
            self.logger.info("Saving current best: {}".format(file_name))
        else:
            self.logger.info("Saving checkpoint: {}".format(params_filename))

    def _resume_checkpoint(self, resume_path):
        """
        从检查点钟加载模型，会加载模型权重，trainer状态，其他的信息
        :param resume_path: 检查点地址
        :return:
        """
        self.logger.info("Loading checkpoint: {} ...".format(resume_path))

        # 加载模型参数
        self.model.load_parameters(resume_path, ctx=self.ctx, ignore_extra=True, allow_missing=True)
        # 加载trainer状态
        trainer_filename = resume_path.replace('.params', '.train_states')
        if os.path.exists(trainer_filename):
            self.trainer.load_states(trainer_filename)

        # 加载其他信息
        other_filename = resume_path.replace('.params', '.info')
        checkpoint = pickle.load(open(other_filename,'rb'))
        self.start_epoch = checkpoint['epoch'] + 1
        self.global_step = checkpoint['global_step']
        self.metrics = checkpoint['metrics']

        self.logger.info("Checkpoint '{}' (epoch {}) loaded".format(resume_path, self.start_epoch))

    def _initialize(self, name, module, *args, **kwargs):
        module_name = self.config[name]['type']
        module_args = self.config[name]['args']
        assert all([k not in module_args for k in kwargs]), 'Overwriting kwargs given in config file is not allowed'
        module_args.update(kwargs)
        return getattr(module, module_name)(*args, **module_args)
