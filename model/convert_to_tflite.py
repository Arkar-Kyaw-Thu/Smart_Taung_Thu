# colabတွင် cell 1နေရာမာ image_model.pyကို ထားပီး run ရန်
# ဒီcodeကို cell 2နေရာမာထားပီး run ရန်

import tensorflow as tf

# ၁. Drive ထဲက .h5 ဖိုင်ကို Load လုပ်ခြင်း
model_path = '/content/drive/MyDrive/corn_combined_model.h5'
model = tf.keras.models.load_model(model_path)

# ၂. TFLite သို့ Convert လုပ်ခြင်း
converter = tf.lite.TFLiteConverter.from_keras_model(model)

# App size သေးငယ်စေရန်နှင့် Speed မြန်စေရန် Optimizations ထည့်သွင်းခြင်း
converter.optimizations = [tf.lite.Optimize.DEFAULT]
tflite_model = converter.convert()

# ၃. Drive ထဲသို့ .tflite ဖိုင်အဖြစ် သိမ်းဆည်းခြင်း
tflite_save_path = '/content/drive/MyDrive/model.tflite'
with open(tflite_save_path, 'wb') as f:
    f.write(tflite_model)

print("✅ TFLite Model ပြောင်းလဲခြင်း အောင်မြင်ပါသည်။ Google Drive ထဲတွင် 'model.tflite' ကို Download ရယူနိုင်ပါပြီ။")