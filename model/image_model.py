# colabတွင် cell 1နေရာမာ ဒီcodeကို ထားပီး run ရန်
# cell 2နေရာမာ convert_to_tflite.pyကို ထားပီး run ရန်

from google.colab import drive # type: ignore
import os

# Google Drive Mount လုပ်ခြင်း
drive.mount('/content/drive')

# Dataset Folder လမ်းကြောင်း (မိမိ Drive အမှန်အတိုင်း ပြင်ပါ)
DATASET_DIR = '/content/drive/MyDrive/corn_dataset'

print("✅ Drive ချိတ်ဆက်ပြီးပါပြီ။")

import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2, EfficientNetB0 # type: ignore
from tensorflow.keras.layers import Dense, GlobalAveragePooling2D, Dropout, Concatenate, Input # type: ignore
from tensorflow.keras.models import Model # type: ignore
from tensorflow.keras.preprocessing.image import ImageDataGenerator # type: ignore
from tensorflow.keras.callbacks import ModelCheckpoint, ReduceLROnPlateau # type: ignore
from sklearn.utils.class_weight import compute_class_weight
import numpy as np

# Settings များ သတ်မှတ်ခြင်း
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 6
NUM_CLASSES = 7

# ၁. Data Generators
train_datagen = ImageDataGenerator(
    rescale=1./255,
    validation_split=0.2
)

train_generator = train_datagen.flow_from_directory(
    DATASET_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode='categorical',
    subset='training',
    shuffle=True
)

val_generator = train_datagen.flow_from_directory(
    DATASET_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode='categorical',
    subset='validation',
    shuffle=False
)

# ၂. Class Weights တွက်ချက်ခြင်း
class_weights = compute_class_weight(
    class_weight='balanced',
    classes=np.unique(train_generator.classes),
    y=train_generator.classes
)
class_weight_dict = dict(enumerate(class_weights))

# ၃. Combined (Ensemble) Model Architecture တည်ဆောက်ခြင်း
input_tensor = Input(shape=(224, 224, 3))

# Base Model 1: MobileNetV2
mobilenet = MobileNetV2(weights='imagenet', include_top=False, input_tensor=input_tensor)
mobilenet.trainable = False
x1 = GlobalAveragePooling2D()(mobilenet.output)

# Base Model 2: EfficientNetB0
efficientnet = EfficientNetB0(weights='imagenet', include_top=False, input_tensor=input_tensor)
efficientnet.trainable = False
x2 = GlobalAveragePooling2D()(efficientnet.output)

# Model နှစ်ခုမှ ရရှိသော Feature များကို ပေါင်းစပ်ခြင်း (Concatenate)
combined = Concatenate()([x1, x2])

# Fully Connected Layers
x = Dense(256, activation='relu')(combined)
x = Dropout(0.4)(x)
predictions = Dense(NUM_CLASSES, activation='softmax')(x)

# Final Combined Model
model = Model(inputs=input_tensor, outputs=predictions)

# ၄. Compile Model
model.compile(
    optimizer=tf.keras.optimizers.Adam(learning_rate=0.0001),
    loss='categorical_crossentropy',
    metrics=['accuracy']
)

model.summary()

# ၅. Save Path & Callbacks
SAVE_MODEL_PATH = '/content/drive/MyDrive/corn_combined_model.h5'

checkpoint = ModelCheckpoint(
    SAVE_MODEL_PATH,
    monitor='val_accuracy',
    save_best_only=True,
    mode='max',
    verbose=1
)

reduce_lr = ReduceLROnPlateau(
    monitor='val_loss',
    factor=0.2,
    patience=3,
    min_lr=1e-6,
    verbose=1
)

# ၆. Start Training
print("\n🚀 MobileNetV2 + EfficientNetB0 Combined Model ကို စတင် Train နေပါသည်...")
history = model.fit(
    train_generator,
    epochs=EPOCHS,
    validation_data=val_generator,
    callbacks=[checkpoint, reduce_lr],
    class_weight=class_weight_dict
)

print(f"\n🎉 Combined Model Training ပြီးပါပြီ! Drive ရှိ '{SAVE_MODEL_PATH}' တွင် သိမ်းဆည်းလိုက်ပါပြီ။")