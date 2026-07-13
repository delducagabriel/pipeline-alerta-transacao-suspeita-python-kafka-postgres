"""
Ponto de entrada principal do pipeline.

Usage:
    python -m src.run producer          # Inicia producer com simulador
    python -m src.run consumer          # Inicia consumer com detector
    python -m src.run dashboard         # Inicia dashboard Streamlit
    python -m src.run all               # Inicia producer + consumer + dashboard
"""

import argparse
import logging
import subprocess
import sys
import time
import os


def setup_logging(level: str = "INFO") -> None:
    """Configura logging formatado para o pipeline."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=(
            "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_producer(args) -> None:
    """Inicia o producer Kafka com simulador de transações."""
    from src.producer import iniciar_producer_simulado

    logger = logging.getLogger(__name__)
    logger.info("Iniciando Producer com simulador...")
    logger.info("TPS: %.1f | Duração: %ds", args.tps, args.duracao)

    iniciar_producer_simulado(tps=args.tps, duracao_segundos=args.duracao)


def run_consumer(args) -> None:
    """Inicia o consumer Kafka com detector de fraude."""
    from src.consumer import FraudConsumer

    logger = logging.getLogger(__name__)
    logger.info("Iniciando Consumer com detector de fraude...")

    consumer = FraudConsumer()
    consumer.connect()
    consumer.consumir()


def run_dashboard(args) -> None:
    """Inicia o dashboard Streamlit."""
    from src.dashboard import main as dashboard_main

    dashboard_main()


def run_all(args) -> None:
    """Inicia producer, consumer e dashboard em conjunto."""
    import threading

    logger = logging.getLogger(__name__)
    logger.info("Iniciando pipeline completo (producer + consumer + dashboard)...")

    # Inicia consumer em thread separada
    def consumer_thread():
        run_consumer(args)

    def producer_thread():
        time.sleep(5)  # Aguarda consumer iniciar
        from src.producer import iniciar_producer_simulado
        iniciar_producer_simulado(tps=args.tps, duracao_segundos=args.duracao)

    t_consumer = threading.Thread(target=consumer_thread, daemon=True)
    t_producer = threading.Thread(target=producer_thread, daemon=True)

    t_consumer.start()
    t_producer.start()

    # Dashboard na thread principal
    try:
        run_dashboard(args)
    except KeyboardInterrupt:
        logger.info("Pipeline encerrado pelo usuário")


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline de Detecção de Transações Suspeitas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python -m src.run producer --tps 20 --duracao 120\n"
            "  python -m src.run consumer\n"
            "  python -m src.run dashboard\n"
            "  python -m src.run all --tps 15\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a executar")

    # Producer
    p_producer = subparsers.add_parser("producer", help="Iniciar producer com simulador")
    p_producer.add_argument("--tps", type=float, default=10,
                            help="Transações por segundo (padrão: 10)")
    p_producer.add_argument("--duracao", type=int, default=60,
                            help="Duração em segundos (padrão: 60)")
    p_producer.set_defaults(func=run_producer)

    # Consumer
    p_consumer = subparsers.add_parser("consumer", help="Iniciar consumer com detector")
    p_consumer.set_defaults(func=run_consumer)

    # Dashboard
    p_dashboard = subparsers.add_parser("dashboard", help="Iniciar dashboard Streamlit")
    p_dashboard.set_defaults(func=run_dashboard)

    # All
    p_all = subparsers.add_parser("all", help="Iniciar pipeline completo")
    p_all.add_argument("--tps", type=float, default=10,
                       help="Transações por segundo (padrão: 10)")
    p_all.add_argument("--duracao", type=int, default=300,
                       help="Duração do producer em segundos (padrão: 300)")
    p_all.set_defaults(func=run_all)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    setup_logging()
    args.func(args)


if __name__ == "__main__":
    main()