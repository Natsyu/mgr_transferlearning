import matplotlib.pyplot as plt
from netparams import NetParams
import torch
from datasetmodel import DatasetModel
import numpy as np
import time
from termcolor import colored


def train_loop(netparams: NetParams, no_improvement=0):

    start_time = time.time()
    valid_loss_min = np.Inf
    train_loss_array = []
    valid_loss_array = []
    train_time_sum = 0
    eval_time_sum = 0

    for epoch in range(1, netparams.n_epochs + 1):

        # early stopping
        if no_improvement >= netparams.max_no_improve_epochs:
            break

        # keep track of training and validation loss
        train_loss = 0.0
        train_loss_tmp = 0.0
        valid_loss = 0.0

        ###################
        # train the model #
        ###################
        train_time = time.time()

        train_loss = train_model(netparams=netparams,
                                 train_loss_tmp=train_loss_tmp,
                                 train_loss=train_loss,
                                 epoch=epoch)

        train_end_time = time.time() - train_time
        print(f"⌛Training epoch {epoch} took {train_end_time:.2f} seconds")
        train_time_sum += train_end_time
        ######################
        # evaluate the model #
        ######################
        eval_time = time.time()
        valid_loss_min = evaluate_model(netparams=netparams,
                                        train_loss=train_loss,
                                        valid_loss=valid_loss,
                                        valid_loss_min=valid_loss_min,
                                        valid_loss_array=valid_loss_array,
                                        train_loss_array=train_loss_array,
                                        epoch=epoch,
                                        no_improvement=no_improvement)

        eval_end_time = time.time() - eval_time
        print(
            f"⌛Evaluating epoch {epoch} took {(eval_end_time):.2f} seconds\n")
        eval_time_sum += eval_end_time

    end_time = time.time()
    print(f"🎓Total learning took {(end_time - start_time):.2f} seconds")
    print(f"🏋️‍♂️Training took {train_time_sum:.2f} seconds")
    print(f"📑Evaluation took {eval_time_sum:.2f} seconds")
    return train_loss_array, valid_loss_array


def train_model(netparams: NetParams,
                train_loss_tmp,
                train_loss,
                epoch):
    netparams.model.train()
    print("Training")
    for batch_i, (data, target) in enumerate(netparams.train_loader):
        # move tensors to GPU if CUDA is available
        if netparams.train_on_gpu:
            data, target = data.cuda(), target.cuda()
        # clear the gradients of all optimized variables
        netparams.optimizer.zero_grad()
        # forward pass: compute predicted outputs by passing inputs to the model
        output = netparams.model(data)
        # calculate the batch loss
        loss = netparams.criterion(output, target)
        # backward pass: compute gradient of the loss with respect to model parameters
        loss.backward()
        # perform a single optimization step (parameter update)
        netparams.optimizer.step()
        # update training loss
        train_loss_tmp += loss.item()
        train_loss += loss.item() * data.size(0)

        if batch_i % 20 == 19:    # print training loss every specified number of mini-batches
            print(
                f'Epoch {epoch}, Batch {batch_i + 1} loss: {(train_loss_tmp / 20):.16f}')
            train_loss_tmp = 0.0
        return train_loss


def evaluate_model(netparams: NetParams,
                   train_loss,
                   valid_loss,
                   valid_loss_min,
                   valid_loss_array,
                   train_loss_array,
                   epoch,
                   no_improvement):
    print('Evaluation')
    netparams.model.eval()
    for batch_i, (data, target) in enumerate(netparams.validation_loader):

        # cuda
        if netparams.train_on_gpu:
            data, target = data.cuda(), target.cuda()

        y = netparams.model(data)
        loss = netparams.criterion(y, target)
        valid_loss += loss.item() * data.size(0)

    train_loss = train_loss / len(netparams.train_loader.sampler)
    valid_loss = valid_loss / len(netparams.validation_loader.sampler)

    # print training/validation statistics
    print(
        f'\nEpoch: {epoch}/{netparams.n_epochs} \tTraining Loss: {train_loss:.6f} \tValidation Loss: {valid_loss:.6f}')
    train_loss_array.append(train_loss)
    valid_loss_array.append(valid_loss)
    # save model if validation loss has decreased
    if valid_loss <= valid_loss_min:
        print(colored(
            f'Validation loss decreased ({valid_loss_min:.6f} --> {valid_loss:.6f}).  Saving model ...', 'green'))
        torch.save(netparams.model.state_dict(), f'{epoch:03d}model_cifar.pt')
        valid_loss_min = valid_loss
        no_improvement = 0
    else:
        no_improvement += 1
        print(colored(f'No improvement for {no_improvement} epochs', 'red'))
    return valid_loss_min


def plot_loss(loss_name: str, loss_array: set):
    min_idx = loss_array.index(min(loss_array))
    plt.plot(loss_array[:min_idx])
    plt.ylabel(loss_name)
    plt.show()


def test_model(netparams: NetParams, working_ds: DatasetModel):
    # track test loss
    test_loss = 0.0
    class_correct = list(0. for i in range(working_ds.class_num))
    class_total = list(0. for i in range(working_ds.class_num))

    netparams.model.eval()  # eval mode
    if netparams.train_on_gpu:
        netparams.model.cuda()

    # iterate over test data
    for data, target in netparams.test_loader:

        if len(target.data) < netparams.batch_size:
            break
        # move tensors to GPU if CUDA is available
        if netparams.train_on_gpu:
            data, target = data.cuda(), target.cuda()
        # forward pass: compute predicted outputs by passing inputs to the model
        output = netparams.model(data)
        # calculate the batch loss
        loss = netparams.criterion(output, target)
        # update  test loss
        test_loss += loss.item() * data.size(0)
        # convert output probabilities to predicted class
        _, pred = torch.max(output, 1)
        # compare predictions to true label
        correct_tensor = pred.eq(target.data.view_as(pred))
        correct = np.squeeze(correct_tensor.numpy()) if not netparams.train_on_gpu else np.squeeze(
            correct_tensor.cpu().numpy())
        # calculate test accuracy for each object class
        for i in range(netparams.batch_size):
            label = target.data[i]
            class_correct[label] += correct[i].item()
            class_total[label] += 1

    # calculate avg test loss
    test_loss = test_loss / len(netparams.test_loader.dataset)
    print('Test Loss: {:.6f}\n'.format(test_loss))

    for i in range(working_ds.class_num):
        if class_total[i] > 0:
            print('Test Accuracy of %5s: %2d%% (%2d/%2d)' % (
                working_ds.classes[i], 100 * class_correct[i] / class_total[i],
                np.sum(class_correct[i]), np.sum(class_total[i])))
        else:
            print('Test Accuracy of %5s: N/A (no training examples)' %
                  (working_ds.classes[i]))

    print('\nTest Accuracy (Overall): %2d%% (%2d/%2d)' % (
        100. * np.sum(class_correct) / np.sum(class_total),
        np.sum(class_correct), np.sum(class_total)))


def plot_test_results(netparams: NetParams, working_ds: DatasetModel):
    # obtain one batch of test images
    dataiter = iter(netparams.test_loader)
    images, labels = dataiter.next()
    images.numpy()

    netparams.model.cpu()
    # get sample outputs
    output = netparams.model(images)
    # convert output probabilities to predicted class
    _, preds_tensor = torch.max(output, 1)
    preds = np.squeeze(preds_tensor.cpu().numpy())

    # plot the images in the batch, along with predicted and true labels
    fig = plt.figure(figsize=(40, 5))
    for idx in np.arange(batch_size):
        ax = fig.add_subplot(2, netparams.batch_size / 2,
                             idx + 1, xticks=[], yticks=[])
        plt.imshow(np.transpose(images[idx], (1, 2, 0)))
        ax.set_title("{}\n({})".format(working_ds.classes[preds[idx]], working_ds.classes[labels[idx]]),
                     color=("green" if preds[idx] == labels[idx].item() else "red"))
