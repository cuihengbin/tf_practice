import tensorflow as tf
from tensorflow.examples.tutorials.mnist import input_data
from utils.prob import *
from utils.nn import *
from utils.image import batchmat_to_tileimg
from utils.data import load_pkl
from draw.attention import *
import time
import os
import matplotlib.pyplot as plt

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('save_dir', '../results/tmnist/vae_dattn',
        """directory to save models.""")
tf.app.flags.DEFINE_integer('n_epochs', 30,
        """number of epochs to run""")
tf.app.flags.DEFINE_integer('n_hid', 400,
        """number of hidden units""")
tf.app.flags.DEFINE_integer('n_lat', 20,
        """number of latent variables""")
tf.app.flags.DEFINE_integer('N', 30,
        """attention size""")
tf.app.flags.DEFINE_boolean('train', True,
        """training (True) vs testing (False)""")

if not os.path.isdir(FLAGS.save_dir):
    os.makedirs(FLAGS.save_dir)

n_hid = FLAGS.n_hid
n_lat = FLAGS.n_lat
N = FLAGS.N
height = 50
width = 50
attunit = AttentionUnit(height, width, 1, N)
n_in = height*width
x = tf.placeholder(tf.float32, shape=[None, n_in])
att_enc = linear(fc(x, 50), 5)
x_att = attunit.read(x, att_enc)
hid_enc = fc(tf.concat(1, [att_enc, x_att]), n_hid)
z_mean = linear(hid_enc, n_lat)
z_log_var = linear(hid_enc, n_lat)
z = gaussian_sample(z_mean, z_log_var)
hid_dec = fc(z, n_hid)
att_dec = linear(hid_dec, 5)
p_att = linear(hid_dec, N*N)
p = tf.nn.sigmoid(attunit.write(p_att, att_dec))

train_xy, valid_xy, test_xy = load_pkl('data/tmnist/tmnist.pkl.gz')
train_x, _ = train_xy
valid_x, _ = valid_xy
test_x, _ = test_xy
batch_size = 100
n_train_batches = len(train_x) / batch_size
n_valid_batches = len(valid_x) / batch_size

neg_ll = bernoulli_neg_ll(x, p)
kld = gaussian_kld(z_mean, z_log_var)
loss = neg_ll + kld
train_op = tf.train.AdamOptimizer().minimize(loss)
saver = tf.train.Saver()
sess = tf.Session()

def train():
    logfile = open(FLAGS.save_dir + '/train.log', 'w', 0)
    logfile.write(('n_in: %d, n_hid: %d, n_lat: %d, N: %d\n' % (n_in, n_hid, n_lat, N)))
    sess.run(tf.initialize_all_variables())
    for i in range(FLAGS.n_epochs):
        start = time.time()
        train_neg_ll = 0.
        train_kld = 0.
        for j in range(n_train_batches):
            batch_x = train_x[j*batch_size:(j+1)*batch_size]
            _, batch_neg_ll, batch_kld = \
                    sess.run([train_op, neg_ll, kld], {x:batch_x})
            train_neg_ll += batch_neg_ll
            train_kld += batch_kld
        train_neg_ll /= n_train_batches
        train_kld /= n_train_batches

        valid_neg_ll = 0.
        valid_kld = 0.
        for j in range(n_valid_batches):
            batch_x = valid_x[j*batch_size:(j+1)*batch_size]
            batch_neg_ll, batch_kld = sess.run([neg_ll, kld], {x:batch_x})
            valid_neg_ll += batch_neg_ll
            valid_kld += batch_kld
        valid_neg_ll /= n_valid_batches
        valid_kld /= n_valid_batches

        line = "Epoch %d (%f sec), train loss %f = %f + %f, valid loss %f = %f + %f" \
                % (i+1, time.time()-start,
                        train_neg_ll+train_kld, train_neg_ll, train_kld,
                        valid_neg_ll+valid_kld, valid_neg_ll, valid_kld)
        print line
        logfile.write(line + '\n')
    logfile.close()
    saver.save(sess, FLAGS.save_dir+'/model.ckpt')

def test():
    saver.restore(sess, FLAGS.save_dir+'/model.ckpt')
    batch_x = test_x[0:100]
    fig = plt.figure('original')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(batch_x, (height, width), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/original.png')

    batch_x_att, p_recon_att, p_recon = \
            sess.run([x_att, tf.nn.sigmoid(p_att), p], {x:batch_x})
    fig = plt.figure('attended')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(batch_x_att, (N, N), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/attended.png')
    fig = plt.figure('reconstructed_attended')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(p_recon_att, (N, N), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/reconstructed_attended.png')
    fig = plt.figure('reconstructed')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(p_recon, (height, width), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/reconstructed.png')

    p_gen_att, p_gen = sess.run([tf.nn.sigmoid(p_att), p],
            {z:np.random.normal(size=(100, n_lat))})
    fig = plt.figure('generated_attended')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(p_gen_att, (N, N), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/generated_attended.png')
    fig = plt.figure('generated')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(p_gen, (height, width), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/generated.png')

    plt.show()

def main(argv=None):
    if FLAGS.train:
        train()
    else:
        test()

if __name__ == '__main__':
    tf.app.run()
