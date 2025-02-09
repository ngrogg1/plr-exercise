"""
Train a CNN.

CL arguments:
--batch-size: int
    input batch size for training (default: 64)
--test-batch-size: int
    input batch size for testing (default: 1000)
--gamma: float
    Learning rate step gamma (default: 0.7)
--no-cuda: bool
    disables CUDA training
--dry-run: bool
    quickly check a single pass
--seed: int
    random seed (default: 1)
--log-interval: int
    how many batches to wait before logging training status
--save-model: bool
    For Saving the current Model
"""

from __future__ import print_function
import argparse
import torch
import torch.optim as optim
from torchvision import datasets, transforms
from torch.optim.lr_scheduler import StepLR
import torch.nn.functional as F
from plr_exercise.models import Net

# Wandb
import wandb

# Optuna
import optuna


def train(args, model, device, train_loader, optimizer, epoch):
    """
    Train the cnn model on the train dataset.
    
    Paramters:

    args: argparse.Namespace
        Command line arguments.
    model: torch.nn.Module
        Model to train.
    device: torch.device
        Device to train on (GPU/CPU).
    train_loader: torch.utils.data.DataLoader
        Training data loader.
    optimizer: torch.optim.Optimizer
        Optimizer for training.
    epoch: int
        Amount of epochs.
    """

    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):

        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()
        optimizer.step()
        if batch_idx % args.log_interval == 0:
            print(
                "Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}".format(
                    epoch,
                    batch_idx * len(data),
                    len(train_loader.dataset),
                    100.0 * batch_idx / len(train_loader),
                    loss.item(),
                )
            )
            if args.dry_run:
                break

            # log metrics to wandb
            wandb.log({"training loss": loss.item()})


def test(model, device, test_loader):
    """
    Calculate and Return the inference loss on the test dataset of the trained cnn model.
    
    Parameters:
    model: torch.nn.Module
        Model to test.
    device: torch.device
        Device to test on (GPU/CPU).
    test_loader: torch.utils.data.DataLoader
        Test data loader.
    
    Returns:
    test_loss: float
        Inference loss of the model.
    """

    model.eval()
    test_loss = 0
    correct = 0

    with torch.no_grad():
        for data, target in test_loader:

            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction="sum").item()  # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()

    test_loss /= len(test_loader.dataset)

    # log metrics to wandb
    wandb.log({"test acc": 100.0 * correct / len(test_loader.dataset), "test loss": test_loss})

    print(
        "\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n".format(
            test_loss, correct, len(test_loader.dataset), 100.0 * correct / len(test_loader.dataset)
        )
    )

    return test_loss


def objective(trial):
    """
    Return and calculate the minimization objective.
    
    Return and calculate the test loss, 
    with the learning rate and epochs as minimization parameters.

    Parameter:
    trial: int
        Current trial number.
    """

    # Training settings
    parser = argparse.ArgumentParser(description="PyTorch MNIST Example")
    parser.add_argument(
        "--batch-size", type=int, default=64, metavar="N", help="input batch size for training (default: 64)"
    )
    parser.add_argument(
        "--test-batch-size", type=int, default=1000, metavar="N", help="input batch size for testing (default: 1000)"
    )
    # parser.add_argument("--epochs", type=int, default=2, metavar="N", help="number of epochs to train (default: 14)")
    # parser.add_argument("--lr", type=float, default=1.0, metavar="LR", help="learning rate (default: 1.0)")
    parser.add_argument("--gamma", type=float, default=0.7, metavar="M", help="Learning rate step gamma (default: 0.7)")
    parser.add_argument("--no-cuda", action="store_true", default=False, help="disables CUDA training")
    parser.add_argument("--dry-run", action="store_true", default=False, help="quickly check a single pass")
    parser.add_argument("--seed", type=int, default=1, metavar="S", help="random seed (default: 1)")
    parser.add_argument("--log-interval", type=int, default=10, metavar="N", help="how many batches to wait before logging training status")
    parser.add_argument("--save-model", action="store_true", default=False, help="For Saving the current Model")
    args = parser.parse_args()
    use_cuda = not args.no_cuda and torch.cuda.is_available()

    torch.manual_seed(args.seed)

    if use_cuda:
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    lr = trial.suggest_float("lr", 0.00001, 0.001)
    epochs = trial.suggest_int("epochs", 1, 10)

    # start a new wandb run to track this script
    wandb.init(
        # set the wandb project where this run will be logged
        project="plr-task_3",
        # track hyperparameters and run metadata
        config={
            "learning_rate": lr,
            "architecture": "CNN",
            "dataset": "MNIST",
            "epochs": epochs,
        },
    )

    train_kwargs = {"batch_size": args.batch_size}
    test_kwargs = {"batch_size": args.test_batch_size}
    if use_cuda:
        cuda_kwargs = {"num_workers": 1, "pin_memory": True, "shuffle": True}
        train_kwargs.update(cuda_kwargs)
        test_kwargs.update(cuda_kwargs)

    transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))])
    dataset1 = datasets.MNIST("../data", train=True, download=True, transform=transform)
    dataset2 = datasets.MNIST("../data", train=False, transform=transform)
    train_loader = torch.utils.data.DataLoader(dataset1, **train_kwargs)
    test_loader = torch.utils.data.DataLoader(dataset2, **test_kwargs)

    model = Net().to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)

    scheduler = StepLR(optimizer, step_size=1, gamma=args.gamma)
    for epoch in range(epochs):
        train(args, model, device, train_loader, optimizer, epoch)
        test_loss = test(model, device, test_loader, epoch)
        scheduler.step()

    if args.save_model:
        torch.save(model.state_dict(), "mnist_cnn.pt")

    return test_loss


def main():
    """Start the optimizing of the cnn model training."""
    
    study = optuna.create_study()
    study.optimize(objective, n_trials=5)
    print(study.best_params)

    artifact_code = wandb.Artifact(name="code", type="code")
    artifact_code.add_dir("C:/Users/nicgr/Documents/GitHub/plr-exercise/scripts/")
    wandb.log_artifact(artifact_code)

    # finish the wandb run, necessary in notebooks
    wandb.finish()


if __name__ == "__main__":
    main()
