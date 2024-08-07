import time
from typing import Optional

from docker import DockerClient, errors, from_env
from docker.models.containers import Container
from halo import Halo
from typer import Argument, Option, Typer, colors, secho

DEFAULT_NETWORK_NAME = "cont_net"

cli = Typer()


def wait_healtcheck(docker: DockerClient, container_id: str) -> None:
    with Halo("waiting for the condition", text_color="green"):
        ready = False
        while not ready:
            container = docker.containers.get(container_id)
            health_status = container.attrs["State"]["Health"]["Status"]
            ready = health_status == "healthy"
            time.sleep(0.1)
    secho("Container is ", nl=False)
    secho("healthy", fg=colors.BRIGHT_GREEN, nl=False)
    secho("!")


def declare_network(docker: DockerClient, network: str) -> None:
    with Halo(f"Creating network {network}", text_color="green"):
        try:
            docker.networks.get(network)
        except errors.NotFound:
            docker.networks.create(
                network,
                attachable=True,
            )


def pull_img(docker: DockerClient, repo: str, tag: str) -> str:
    with Halo(f"Pulling image {repo}:{tag}", text_color="green"):
        img = docker.images.pull(repo, tag=tag)
    return img.attrs["RepoTags"][0]


def print_network_settings(docker: DockerClient, container_id: str) -> None:
    secho("Container IPs:")
    container = docker.containers.get(container_id)
    networks = container.attrs["NetworkSettings"]["Networks"]
    for network, nconfig in networks.items():
        secho(f"\t{network}: ", nl=False)
        secho(nconfig["IPAddress"], fg=colors.GREEN)


def container_ready(docker: DockerClient, cont: Container):
    secho("Container ", nl=False)
    secho(cont.name, nl=False)
    secho(" with id ", nl=False)
    secho(cont.short_id, nl=False, fg=colors.GREEN)
    secho(" successfully started")
    wait_healtcheck(docker, cont.id)
    print_network_settings(docker, cont.id)


@cli.command(help="Run postgres container")
def pg(
    name: Optional[str] = Argument(None, help="Container name"),
    db_name: str = Option(
        "postgres",
        help="Name of the database. User and password match this value",
    ),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    port: int = Option(5432, help="Host port to expose"),
    tag: str = Option("16.3-bookworm", help="Image tag to use"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "postgres", tag)
    declare_network(docker, network)
    volumes = None
    if name is not None:
        volumes = {f"{name}-pg-db": {"bind": "/var/lib/postgresql/data", "mode": "rw"}}
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "pg",
        healthcheck={
            "test": f"pg_isready -U {db_name}",
            "interval": 2 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 40,
        },
        ports={
            "5432": port,
        },
        volumes=volumes,
        environment={
            "POSTGRES_PASSWORD": db_name,
            "POSTGRES_USER": db_name,
            "POSTGRES_DB": db_name,
        },
    )
    container_ready(docker, container)


@cli.command(help="Run timescaledb container")
def timescale(
    name: Optional[str] = Argument(None, help="Container name"),
    db_name: str = Option(
        "timescale",
        help="Name of the database. User and password match this value",
    ),
    port: int = Option(5432, help="Host port to expose"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("2.15.3-pg16", help="Image tag to use"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "timescale/timescaledb", tag)
    declare_network(docker, network)
    volumes = None
    if name is not None:
        volumes = {f"{name}-ts-db": {"bind": "/var/lib/postgresql/data", "mode": "rw"}}
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "timescale",
        healthcheck={
            "test": f"pg_isready -U {db_name}",
            "interval": 2 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 40,
        },
        ports={
            "5432": port,
        },
        volumes=volumes,
        environment={
            "POSTGRES_PASSWORD": db_name,
            "POSTGRES_USER": db_name,
            "POSTGRES_DB": db_name,
        },
    )
    container_ready(docker, container)


@cli.command(help="Run rabbitMQ container")
def rmq(
    name: Optional[str] = Argument(None, help="Container name"),
    port: int = Option(5672, help="Port to open for AMQP protocol"),
    ui_port: int = Option(15672, help="Port to open for management UI"),
    username: str = Option("guest", help="Admin username"),
    password: str = Option("guest", help="Admin password"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("3.13-management", help="Image tag to use"),
):
    docker = from_env()
    img = pull_img(docker, "rabbitmq", tag)
    declare_network(docker, network)
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "rmq",
        healthcheck={
            "test": "rabbitmq-diagnostics check_running -q",
            "interval": 3 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 50,
        },
        ports={
            "5672": port,
            "15672": ui_port,
        },
        environment={
            "RABBITMQ_DEFAULT_USER": username,
            "RABBITMQ_DEFAULT_PASS": password,
            "RABBITMQ_DEFAULT_VHOST": "/",
        },
    )
    container_ready(docker, container)


@cli.command(help="Run redis container")
def redis(
    name: Optional[str] = Argument(None, help="Name of the container"),
    port: int = Option(6379, help="Port to open for redis protocol"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("7-bookworm", help="Image tag to use"),
):
    docker = from_env()
    img = pull_img(docker, "redis", tag)
    declare_network(docker, network)
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "redis",
        healthcheck={
            "test": "redis-cli ping",
            "interval": 1 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 50,
        },
        ports={
            "6379": port,
        },
    )
    container_ready(docker, container)


@cli.command(help="Run scylla container")
def scylla(
    name: Optional[str] = Argument(None, help="Container name"),
    port: int = Option(9042, help="Port to open for scylla"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("6.0.1", help="Image tag"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "scylladb/scylla", tag)
    declare_network(docker, network)
    volumes = None
    if name is not None:
        volumes = {f"{name}-scylla-db": {"bind": "/var/lib/scylla", "mode": "rw"}}
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "scylla",
        command=["--skip-wait-for-gossip-to-settle", "0"],
        healthcheck={
            "test": "cqlsh -e 'select * from system.local'",
            "interval": 5 * 1000 * 1000000,
            "timeout": 5 * 1000 * 1000000,
            "retries": 60,
        },
        ports={
            "9042": port,
        },
        volumes=volumes,
    )
    container_ready(docker, container)


@cli.command(help="Run NATS container")
def nats(
    name: Optional[str] = Argument(None, help="Container name"),
    port: int = Option(4222, help="Port to publish for nats protocol"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    tag: str = Option("2.9-alpine", help="Image tag"),
):
    docker = from_env()
    img = pull_img(docker, "nats", tag)
    declare_network(docker, network)
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "nats",
        command=["-m", "8222", "--jetstream"],
        healthcheck={
            "test": [
                "CMD",
                "sh",
                "-c",
                "wget http://localhost:8222/healthz -q -O - | xargs | grep ok || exit 1",
            ],
            "interval": 5 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 20,
        },
        ports={
            "4222": port,
        },
    )
    container_ready(docker, container)


@cli.command(help="Run zookeeper container")
def zk(
    name: Optional[str] = Argument(None, help="Container name"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    port: int = Option(2181, help="Host port to expose"),
    tag: str = Option("3.9.2", help="Image tag to use"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "bitnami/zookeeper", tag)
    declare_network(docker, network)
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=name or "zk",
        healthcheck={
            "test": "zkServer.sh status",
            "interval": 1 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 30,
        },
        ports={
            "2181": port,
        },
        environment={
            "ALLOW_ANONYMOUS_LOGIN": "yes",
            "ZOO_LOG_LEVEL": "ERROR",
        },
    )
    container_ready(docker, container)


@cli.command(help="Run kafka container")
def kafka(
    name: Optional[str] = Argument(None, help="Container name"),
    network: str = Option(
        DEFAULT_NETWORK_NAME,
        help="Network name to attach container to",
    ),
    port: int = Option(9094, help="Host port to expose"),
    tag: str = Option("3.7-debian-12", help="Image tag to use"),
) -> None:
    docker = from_env()
    img = pull_img(docker, "bitnami/kafka", tag)
    declare_network(docker, network)
    hostname = name or "kafka"
    container = docker.containers.run(
        name=name,
        image=img,
        remove=True,
        detach=True,
        network=network,
        hostname=hostname,
        healthcheck={
            "test": "kafka-topics.sh --list --bootstrap-server localhost:9092",
            "interval": 1 * 1000 * 1000000,
            "timeout": 3 * 1000 * 1000000,
            "retries": 30,
        },
        ports={
            "9094": port,
        },
        environment={
            "KAFKA_CFG_NODE_ID": "0",
            "KAFKA_CFG_PROCESS_ROLES": "controller,broker",
            "KAFKA_CFG_LISTENERS": "PLAINTEXT://:9092,CONTROLLER://:9093,EXTERNAL://:9094",
            "KAFKA_CFG_ADVERTISED_LISTENERS": "PLAINTEXT://kafka:9092,EXTERNAL://localhost:9094",
            "KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP": "CONTROLLER:PLAINTEXT,EXTERNAL:PLAINTEXT,PLAINTEXT:PLAINTEXT",
            "KAFKA_CFG_CONTROLLER_QUORUM_VOTERS": f"0@{hostname}:9093",
            "KAFKA_CFG_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
            "KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE": "true",
            "KAFKA_CFG_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        },
    )
    container_ready(docker, container)


def main():
    cli()


if __name__ == "__main__":
    main()
