Convolutional Recurrent Neural Network
======================================

This software implements the Convolutional Recurrent Neural Network (CRNN) in pytorch.
Origin software could be found in [crnn](https://github.com/bgshih/crnn)


## Requirements
* pytorch 1.3+
* torchvision 0.4+

## Data Preparation
Prepare a text in the following format
```
/path/to/img/img.jpg label
...
```

## Train
1. config the `dataset['train']['dataset']['data_path']`,`dataset['validate']['dataset']['data_path']` in [config.yaml](config/icdar2015.yaml)
2. generate alphabet
use fellow script to generate `alphabet.py` in the some folder with `train.py` 
```sh
python3 utils/get_keys.py
```
2. use following script to run
```sh
python3 train.py --config_path config.yaml
```

## Predict 
[predict.py](src/scripts/predict.py) is used to inference on single image

1. config `model_path`, `img_path` in [predict.py](src/scripts/predict.py)
2. use following script to predict
```sh
python3 predict.py
```