import tensorflow as tf
from utils.prob import *
from utils.nn import *
from utils.image import batchmat_to_tileimg
from utils.data import load_pkl
from draw.attention import *
import time
import os
import matplotlib.pyplot as plt

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('save_dir', '../results/dmnist/dvae_dattn',
        """directory to save models.""")
tf.app.flags.DEFINE_integer('n_epochs', 30,
        """number of epochs to run""")
tf.app.flags.DEFINE_integer('n_hid', 500,
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
height = 56
width = 56
attunit = AttentionUnit(height, width, 1, N)
n_in = height*width

x = tf.placeholder(tf.float32, [None, n_in])

with tf.variable_scope('dvae'):
    hid_t_enc = fc(x, n_hid)
    z0_t_mean = linear(hid_t_enc, n_lat)
    z0_t_log_var = linear(hid_t_enc, n_lat)
    z0_t = gaussian_sample(z0_t_mean, z0_t_log_var)
    trans0 = to_att(fc(z0_t, 50))
    x_att0 = tf.clip_by_value(attunit.read(x, trans0, delta_max=0.5), 0, 1)
    hid_c_enc = fc(x_att0, n_hid)
    z0_c_mean = linear(hid_c_enc, n_lat)
    z0_c_log_var = linear(hid_c_enc, n_lat)
    z0_c = gaussian_sample(z0_c_mean, z0_c_log_var)
    hid_c_dec = fc(z0_c, n_hid)
    p_att0 = fc(hid_c_dec, N*N, activation_fn=tf.nn.sigmoid)
p0 = attunit.write(p_att0, trans0, delta_max=0.5)
res = x - tf.clip_by_value(p0, 0, 1)
with tf.variable_scope('dvae', reuse=True):
    hid_t_enc = fc(res, n_hid)
    z1_t_mean = linear(hid_t_enc, n_lat)
    z1_t_log_var = linear(hid_t_enc, n_lat)
    z1_t = gaussian_sample(z1_t_mean, z1_t_log_var)
    trans1 = to_att(fc(z1_t, 50))
    x_att1 = tf.clip_by_value(attunit.read(res, trans1, delta_max=0.5), 0, 1)
    hid_c_enc = fc(x_att1, n_hid)
    z1_c_mean = linear(hid_c_enc, n_lat)
    z1_c_log_var = linear(hid_c_enc, n_lat)
    z1_c = gaussian_sample(z1_c_mean, z1_c_log_var)
    hid_c_dec = fc(z1_c, n_hid)
    p_att1 = fc(hid_c_dec, N*N, activation_fn=tf.nn.sigmoid)
p1 = attunit.write(p_att1, trans1, delta_max=0.5)
p = tf.clip_by_value(p0 + p1, 0, 1)

neg_ll = bernoulli_neg_ll(x, p)
kld = gaussian_kld(z0_t_mean, z0_t_log_var) + \
        gaussian_kld(z0_c_mean, z0_c_log_var) + \
        gaussian_kld(z1_t_mean, z1_t_log_var) + \
        gaussian_kld(z1_c_mean, z1_c_log_var)
loss = neg_ll + kld

train_x, valid_x, test_x = load_pkl('data/dmnist/dmnist.pkl.gz')
batch_size = 100
n_train_batches = len(train_x) / batch_size
n_valid_batches = len(valid_x) / batch_size

learning_rate = tf.placeholder(tf.float32)
train_op = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(loss)
saver = tf.train.Saver()
sess = tf.Session()

def train():
    logfile = open(FLAGS.save_dir + '/train.log', 'w', 0)
    logfile.write(('n_in: %d, n_hid: %d, n_lat: %d\n' % (n_in, n_hid, n_lat)))
    sess.run(tf.initialize_all_variables())
    lr = 0.001
    for i in range(FLAGS.n_epochs):
        start = time.time()
        train_neg_ll = 0.
        train_kld = 0.
        for j in range(n_train_batches):
            batch_x = train_x[j*batch_size:(j+1)*batch_size]
            _, batch_neg_ll, batch_kld = \
                    sess.run([train_op, neg_ll, kld], {x:batch_x, learning_rate:lr})
            train_neg_ll += batch_neg_ll
            train_kld += batch_kld
        train_neg_ll /= n_train_batches
        train_kld /= n_train_batches
        if (i+1) % 3 == 0:
            lr = lr * 0.8

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

    fa, sa = sess.run([x_att0, x_att1], {x:batch_x})
    plt.figure('first att')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(fa, (N, N), (10, 10)))

    plt.figure('second att')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(sa, (N, N), (10, 10)))

    fa, sa = sess.run([p0, p1], {x:batch_x})
    plt.figure('first recon')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(fa, (height, width), (10, 10)))
    plt.figure('second recon')
    plt.gray()
    plt.axis('off')
    plt.imshow(batchmat_to_tileimg(sa, (height, width), (10, 10)))


    fig = plt.figure('reconstructed')
    plt.gray()
    plt.axis('off')
    p_recon = sess.run(p, {x:batch_x})
    plt.imshow(batchmat_to_tileimg(p_recon, (height, width), (10, 10)))
    fig.savefig(FLAGS.save_dir+'/reconstructed.png')

    p_gen = sess.run(p, {z0_c:np.random.normal(size=(100, n_lat)),
                        z0_t:np.random.normal(size=(100, n_lat)),
                        z1_c:np.random.normal(size=(100, n_lat)),
                        z1_t:np.random.normal(size=(100, n_lat))})
    I_gen = batchmat_to_tileimg(p_gen, (height, width), (10, 10))
    fig = plt.figure('generated')
    plt.gray()
    plt.axis('off')
    plt.imshow(I_gen)
    fig.savefig(FLAGS.save_dir+'/generated.png')

    plt.show()

def main(argv=None):
    if FLAGS.train:
        train()
    else:
        test()

if __name__ == '__main__':
    tf.app.run()
