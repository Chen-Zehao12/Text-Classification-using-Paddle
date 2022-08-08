from fastapi import APIRouter
from models.Text import Text
import paddle.inference as paddle_infer
import json
import numpy as np
import paddlenlp as ppnlp
from paddlenlp.data import Tuple, Pad

router = APIRouter(
    prefix='/chinese',
    tags=['Your chinese api name']
)


def init(model_path):
    # 1. 创建配置对象，设置预测模型路径
    config = paddle_infer.Config(model_path + "/model.pdmodel", model_path + "/model.pdiparams")
    # 设置开启内存/显存复用
    config.enable_memory_optim()
    # 去除 Paddle Inference 运行中的 LOG
    config.disable_glog_info()
    # 启用 GPU 进行预测 - 初始化 GPU 显存 100M, Deivce_ID 为 0
    config.enable_use_gpu(100, 0)

    # 2. 根据配置内容创建推理引擎
    predictor = paddle_infer.create_predictor(config)
    tokenizer = ppnlp.transformers.RobertaTokenizer.from_pretrained(model_path)

    # 定义要进行分类的类别
    with open(model_path + '/label_map.json') as f:
        label_map_str = json.load(f)
    label_map = {}
    for k, v in label_map_str.items():
        label_map[int(k)] = v

    return predictor, tokenizer, label_map


def predict(text, predictor, tokenizer, label_map, max_seq_len=256):
    # tokenizer处理为模型可接受的格式
    encoded_inputs = tokenizer(text=text, max_seq_len=max_seq_len)
    example = (encoded_inputs["input_ids"], encoded_inputs["token_type_ids"])

    batchify_fn = lambda samples, fn=Tuple(
        Pad(axis=0, pad_val=tokenizer.pad_token_id),  # input id
        Pad(axis=0, pad_val=tokenizer.pad_token_id),  # segment id
    ): fn(samples)

    data = batchify_fn([example])

    # 获取输入句柄
    input_handles = [
        predictor.get_input_handle(name)
        for name in predictor.get_input_names()
    ]
    # 设置输入数据
    for input_field, input_handle in zip(data, input_handles):
        input_handle.copy_from_cpu(input_field)

    # 4. 执行预测
    predictor.run()

    # 获取输出
    output_names = predictor.get_output_names()
    output_handle = predictor.get_output_handle(output_names[0])
    output_data = output_handle.copy_to_cpu()  # numpy.ndarray类型

    idx_top3 = list(reversed(np.argsort(output_data[0])))[:3]
    labels = [label_map[i] for i in idx_top3]

    return labels


model_path = 'models/Chinese'
predictor, tokenizer, label_map = init(model_path)


@router.post("/")
def ipc_chinese_classifier(text: Text):
    if not text.data:
        return {'result': '请输入文本'}

    labels = predict(text.data, predictor, tokenizer, label_map)
    return {'result': labels}
