import tensorflow as tf
from tensorflow.contrib import layers
import numpy as np
import time
import matplotlib.pyplot as plt
from utils.data import load_pkl
from utils.image import batchmat_to_tileimg, batchimg_to_tileimg
from stn.spatial_transformer import spatial_transformer, loc_last

fc = layers.fully_connected
conv = layers.convolution2d
pool = layers.max_pool2d
flat = layers.flatten

def gaussian_sample(mean, log_var):
    eps = tf.random_normal(tf.shape(log_var))
    return mean + tf.mul(eps, tf.exp(0.5*log_var))

def gaussian_kld(mean, log_var):
    return tf.reduce_mean(
            -0.5*tf.reduce_sum(1+log_var-tf.pow(mean,2)-tf.exp(log_var), 1))

def bernoulli_neg_ll(x, p, eps=1.0e-10):
    return tf.reduce_mean(
            -tf.reduce_sum(x*tf.log(p+eps)+(1.-x)*tf.log(1-p+eps), 1))

n_hid = 500
n_lat = 20
h = 60
w = 60
h_trans = 20
w_trans = 20

batch_size = 100
x = tf.placeholder(tf.float32, [batch_size, h*w])
x_img = tf.reshape(x, [-1, h, w, 1])
h_enc = fc(x, n_hid)
loc_enc = loc_last(fc(h_enc, 50))
x_trans = flat(spatial_transformer(x_img, loc_enc, [h_trans, w_trans]))
h_enc = fc(tf.concat(1, [x_trans, h_enc]), n_hid)
z_mean = fc(h_enc, n_lat, activation_fn=None)
z_log_var = fc(h_enc, n_lat, activation_fn=None)
z = gaussian_sample(z_mean, z_log_var)

h_dec = fc(z, n_hid)
p_trans = tf.reshape(fc(h_dec, h_trans*w_trans, activation_fn=tf.nn.sigmoid),
        [-1, h_trans, w_trans, 1])
loc_dec = loc_last(fc(h_dec, 50))
p = tf.clip_by_value(flat(spatial_transformer(p_trans, loc_dec, [h, w])),
        0, 1)

neg_ll = bernoulli_neg_ll(x, p)
kld = gaussian_kld(z_mean, z_log_var)
loss = neg_ll + kld
train_step = tf.train.AdamOptimizer().minimize(loss)

train_xy, _, test_xy = load_pkl('data/tmnist/tmnist.pkl.gz')
train_x, _ = train_xy
test_x, _ = test_xy

batch_size = 100
n_train_batches = len(train_x)/batch_size
n_test_batches = len(test_x)/batch_size

n_epochs = 10
with tf.Session() as sess:
    sess.run(tf.initialize_all_variables())
    for i in range(n_epochs):
        start = time.time()
        train_neg_ll = 0.
        train_kld = 0.
        for j in range(n_train_batches):
            batch_x = train_x[j*batch_size:(j+1)*batch_size]
            _, batch_neg_ll, batch_kld = sess.run([train_step, neg_ll, kld],
                    feed_dict={x:batch_x})
            train_neg_ll += batch_neg_ll
            train_kld += batch_kld
        train_neg_ll /= n_train_batches
        train_kld /= n_train_batches
        print "Epoch %d (%.3f sec), train neg ll %f, train kld %f" \
                % (i+1, time.time()-start, train_neg_ll, train_kld)
        np.random.shuffle(train_x)
    I_orig = batchmat_to_tileimg(test_x[0:batch_size], (h, w), (10, 10))
    p_test = sess.run(p, feed_dict={x:test_x[0:batch_size]})
    I_recon = batchmat_to_tileimg(p_test, (h, w), (10, 10))
    x_att_test = sess.run(x_trans, feed_dict={x:test_x[0:batch_size]})
    I_att = batchmat_to_tileimg(x_att_test, (h_trans, w_trans), (10, 10))
    p_gen = sess.run(p, feed_dict={z:np.random.normal(size=(batch_size,n_lat))})
    I_gen = batchmat_to_tileimg(p_gen, (h, w), (10, 10))
    plt.figure("original")
    plt.gray()
    plt.axis('off')
    plt.imshow(I_orig)
    plt.figure("reconstructed")
    plt.imshow(I_recon)
    plt.figure("attended")
    plt.imshow(I_att)
    plt.figure("generated")
    plt.imshow(I_gen)
    plt.show()
