# SiteVerum electrical pole checkpoint

`pole_yolo11s_best.pt` is a four-class object detector. Mark Urupa captured the training imagery internally and used it for labeling and fine-tuning. The checkpoint was initialized from Ultralytics **YOLO11s object detection** weights (`yolo11s.pt`) and fine-tuned with Ultralytics `8.4.49`. [Ultralytics YOLO11](https://docs.ultralytics.com/models/yolo11/) · [Upstream YOLO11s weights](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11s.pt)

The checkpoint and corresponding SiteVerum source are distributed under AGPL-3.0. The internally captured training imagery and annotations are private. [License](../../LICENSE) · [Ultralytics licensing](https://www.ultralytics.com/license)

## Download and use

Download [`pole_yolo11s_best.pt`](https://github.com/markfishurupa-dot/siteverum/releases/download/v2.1.0/pole_yolo11s_best.pt). Its SHA-256 is `80f281ec613757df2934b258afa9b578ae074af16e7393b87cd2a1b33e283cb6`. It predicts `pole_beton` (concrete), `pole_generic`, `pole_metal` and `pole_wood`.

Place the checkpoint in `deploy/module-models/` for the default model, or upload it with **Add model** and choose it in **YOLO model**. The checkpoint provides per-photo detections. The SiteVerum module estimates map locations from multiple detections and uses the survey's camera and GPS information.

## Training configuration

The checkpoint records pretrained initialization, 100 configured epochs, batch size 8, image size 832 pixels, optimizer selection `auto`, and seed 0. The command below uses those recorded settings with a YOLO-format dataset you supply. [Ultralytics training reference](https://docs.ultralytics.com/modes/train/)

```sh
python -m pip install ultralytics==8.4.49
yolo detect train model=yolo11s.pt data=data.yaml pretrained=True epochs=100 batch=8 imgsz=832 optimizer=auto seed=0
```

Use the same class order in your dataset configuration. Point `path` to the root of your dataset, with matching YOLO labels under `train/labels` and `val/labels`.

```yaml
path: /path/to/pole-dataset
train: train/images
val: val/images
names:
  0: pole_beton
  1: pole_generic
  2: pole_metal
  3: pole_wood
```

Check recognition and location quality on representative surveys before relying on results from a different territory, camera mount, or pole population.
